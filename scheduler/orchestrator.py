"""Main trading loop orchestrator for Aegis.

APScheduler-based scheduler that:
- Runs the 30-min trading cycle on each closed candle
- Retrains models every 7 days
- Checks funding rate every 8 hours
- Health checks every hour
- Sends daily report at 00:00 UTC
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from config.settings import settings

logger = logging.getLogger(__name__)


class TradingOrchestrator:
    """Coordinates all Aegis trading components in the main loop.

    Usage:
        orch = TradingOrchestrator()
        orch.start()
        # ... runs until orch.stop() is called
    """

    def __init__(self) -> None:
        self._scheduler = BackgroundScheduler(timezone="UTC")
        self._running = False
        self._emergency_stop = False

        # Lazy-loaded components (initialised in start())
        self._executor = None
        self._order_manager = None
        self._storage = None
        self._feature_engineer = None
        self._ensemble = None
        self._signal_converter = None
        self._position_manager = None
        self._risk_engine = None
        self._decision_logger = None
        self._realtime_feed = None
        self._metrics = None
        self._telegram = None
        self._trainer = None

        self._current_funding_rate: float = 0.0
        self._start_balance: float = 0.0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Initialise all components and start the scheduler."""
        logger.info("%s Orchestrator starting...", settings.log_tag)
        self._init_components()
        self._setup_schedules()
        self._scheduler.start()
        self._running = True
        self._telegram.notify_system_start()
        logger.info("%s Orchestrator running.", settings.log_tag)

    def stop(self, reason: str = "Manual stop") -> None:
        """Gracefully stop the orchestrator."""
        logger.info("%s Orchestrator stopping: %s", settings.log_tag, reason)
        self._running = False
        self._scheduler.shutdown(wait=False)
        if self._telegram:
            self._telegram.notify_system_stop(reason)
        if self._metrics:
            self._metrics.set_running(False)
        logger.info("%s Orchestrator stopped.", settings.log_tag)

    def emergency_stop(self) -> None:
        """Emergency stop: close all positions immediately then stop."""
        logger.error("%s EMERGENCY STOP triggered!", settings.log_tag)
        self._emergency_stop = True
        try:
            if self._executor:
                self._executor.close_position(settings.TRADING_SYMBOL)
                logger.info("%s Emergency close executed.", settings.log_tag)
        except Exception as exc:
            logger.error("%s Emergency close failed: %s", settings.log_tag, exc)
        finally:
            self.stop(reason="Emergency stop")

    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # Component initialisation
    # ------------------------------------------------------------------

    def _init_components(self) -> None:
        from data.storage import Storage
        from data.feature_engineer import compute_features
        from models.ensemble import EnsembleModel
        from models.trainer import ModelTrainer
        from strategy.signal_converter import SignalConverter
        from strategy.position_manager import PositionManager
        from strategy.decision_logger import DecisionLogger
        from risk.risk_engine import RiskEngine
        from data.realtime_feed import RealtimeFeed
        from monitor.metrics import MetricsCollector
        from monitor.telegram_bot import TelegramBot
        from execution.binance_executor import BinanceExecutor
        from execution.order_manager import OrderManager

        self._storage = Storage()
        self._storage.init_db()

        self._executor = BinanceExecutor()
        self._executor.initialize_futures(
            settings.TRADING_SYMBOL,
            settings.LEVERAGE,
            settings.MARGIN_TYPE,
        )
        self._order_manager = OrderManager(self._executor, self._storage)

        self._ensemble = EnsembleModel()
        try:
            self._ensemble.load("models/saved/ensemble.pkl")
            logger.info("%s Ensemble model loaded.", settings.log_tag)
        except Exception:
            logger.warning("%s No saved ensemble model — will need training.", settings.log_tag)

        self._trainer = ModelTrainer(storage=self._storage)
        self._signal_converter = SignalConverter()
        self._position_manager = PositionManager()
        self._risk_engine = RiskEngine()
        self._decision_logger = DecisionLogger(self._storage)
        self._metrics = MetricsCollector()
        self._telegram = TelegramBot()

        # Wire risk engine callbacks
        self._risk_engine.on_emergency_close = self.emergency_stop
        self._risk_engine.on_reduce_position = self._reduce_position
        self._risk_engine.on_telegram_alert = self._telegram.send_raw

        # Initialise risk engine with opening balance
        balance = self._executor.get_balance()
        self._start_balance = balance.get("total", 0.0)
        self._risk_engine.initialise(self._start_balance)
        self._metrics.set_running(True)

        logger.info(
            "%s Components initialised. Balance: %.2f USDT",
            settings.log_tag,
            self._start_balance,
        )

    def _setup_schedules(self) -> None:
        """Register all periodic jobs."""
        # 30-min candle loop — driven by candle close callback; fallback poll every 30 min
        self._scheduler.add_job(
            self._run_trading_cycle_safe,
            trigger=IntervalTrigger(minutes=30),
            id="trading_cycle",
            name="30min trading cycle",
            max_instances=1,
            coalesce=True,
        )
        # Retrain every 7 days
        self._scheduler.add_job(
            self._retrain_models,
            trigger=IntervalTrigger(days=7),
            id="retrain",
            name="Weekly model retrain",
            max_instances=1,
        )
        # Funding rate check every 8 hours
        self._scheduler.add_job(
            self._check_funding_rate,
            trigger=IntervalTrigger(hours=8),
            id="funding",
            name="Funding rate check",
            max_instances=1,
        )
        # Hourly health check
        self._scheduler.add_job(
            self._health_check,
            trigger=IntervalTrigger(hours=1),
            id="health",
            name="Hourly health check",
            max_instances=1,
        )
        # Daily report at 00:00 UTC
        self._scheduler.add_job(
            self._send_daily_report,
            trigger=CronTrigger(hour=0, minute=0, timezone="UTC"),
            id="daily_report",
            name="Daily report",
            max_instances=1,
        )

    # ------------------------------------------------------------------
    # Main trading cycle (steps 1-9)
    # ------------------------------------------------------------------

    def on_candle_closed(self, candle: dict) -> None:
        """Callback from RealtimeFeed when a candle closes — triggers the cycle."""
        self._run_trading_cycle_safe(candle=candle)

    def _run_trading_cycle_safe(self, candle: dict | None = None) -> None:
        """Wrapper that catches exceptions so the scheduler doesn't die."""
        if self._emergency_stop:
            return
        try:
            self._run_trading_cycle(candle)
        except Exception as exc:
            logger.error(
                "%s Trading cycle error: %s", settings.log_tag, exc, exc_info=True
            )
            if self._metrics:
                self._metrics.set_error(str(exc))

    def _run_trading_cycle(self, candle: dict | None = None) -> None:
        """Execute one complete 30-min trading cycle (steps 1–9)."""
        if not self._running:
            return

        logger.info("%s === Trading cycle start ===", settings.log_tag)

        # ---- Step 1: Get latest candle data -----------------------------
        candle_data = candle or self._fetch_latest_candle()
        if candle_data is None:
            logger.warning("%s No candle data available, skipping cycle.", settings.log_tag)
            return

        current_price = float(candle_data.get("close", 0))
        candle_ts = candle_data.get("timestamp", "")

        # ---- Step 2: Calculate features ---------------------------------
        import pandas as pd
        from data.feature_engineer import compute_features

        candles_df = self._storage.get_recent_candles(limit=200)
        if candles_df is None or len(candles_df) < 50:
            logger.warning("%s Insufficient candle history for features.", settings.log_tag)
            return

        funding_df = self._storage.get_recent_funding_rates(limit=50)
        features_df = compute_features(candles_df, funding_df)

        if features_df.empty:
            logger.warning("%s Feature computation returned empty df.", settings.log_tag)
            return

        feature_row = features_df.iloc[-1]
        feature_cols = [c for c in features_df.columns if c != "timestamp"]
        X = feature_row[feature_cols].values.reshape(1, -1)

        # ---- Step 3: Run ensemble model → signal ------------------------
        try:
            prediction = float(self._ensemble.predict(X)[0])
        except Exception as exc:
            logger.error("%s Model prediction failed: %s", settings.log_tag, exc)
            return

        # ---- Step 4: Convert signal -------------------------------------
        signal = self._signal_converter.convert(prediction)
        logger.info(
            "%s Signal: %s z=%.2f size=%.2f reason=%s",
            settings.log_tag,
            signal.direction,
            signal.z_score,
            signal.size_ratio,
            signal.reason,
        )

        # ---- Step 5: Risk check -----------------------------------------
        balance = self._executor.get_balance()
        balance_total = balance.get("total", 0.0)

        order_usdt = balance_total * signal.size_ratio * settings.MAX_POSITION_RATIO
        pos_raw = self._executor.get_position(settings.TRADING_SYMBOL)
        current_pos_usdt = pos_raw.get("size", 0.0) * current_price

        risk_result = self._risk_engine.check_pre_order(
            order_usdt=order_usdt,
            account_balance=balance_total,
            current_position_usdt=current_pos_usdt,
        )

        if not risk_result.passed:
            logger.info(
                "%s Risk check failed: %s", settings.log_tag, risk_result.reason
            )
            self._risk_engine.tick_candle()
            return

        # ---- Step 6: Execute orders -------------------------------------
        self._position_manager.update_from_exchange(
            side=pos_raw.get("side") or "FLAT",
            size=pos_raw.get("size", 0.0),
            entry_price=pos_raw.get("entry_price", 0.0),
            mark_price=current_price,
            liquidation_price=pos_raw.get("liquidation_price", 0.0),
        )

        intent = self._position_manager.compute_order_intent(
            target_direction=signal.direction,
            target_ratio=signal.size_ratio,
            account_balance=balance_total,
        )

        if intent.action != "NONE" and signal.direction != "FLAT":
            self._execute_intent(intent, current_price)

        # ---- Step 7: Update position/PnL --------------------------------
        pos_updated = self._executor.get_position(settings.TRADING_SYMBOL)
        self._position_manager.update_from_exchange(
            side=pos_updated.get("side") or "FLAT",
            size=pos_updated.get("size", 0.0),
            entry_price=pos_updated.get("entry_price", 0.0),
            mark_price=current_price,
            liquidation_price=pos_updated.get("liquidation_price", 0.0),
        )

        # ---- Step 8: Risk monitoring (Stage 2) --------------------------
        stage2 = self._risk_engine.monitor_position(
            entry_price=pos_updated.get("entry_price", 0.0),
            current_price=current_price,
            position_side=(pos_updated.get("side") or "FLAT").upper(),
            position_size=pos_updated.get("size", 0.0),
            leverage=settings.LEVERAGE,
            account_equity=balance_total,
            liquidation_price=pos_updated.get("liquidation_price", 0.0),
            funding_rate=self._current_funding_rate,
        )

        if stage2.emergency_close:
            logger.error(
                "%s Stage 2 emergency close: %s", settings.log_tag, stage2.message
            )
            self._executor.close_position(settings.TRADING_SYMBOL)
        elif stage2.stop_loss_triggered or stage2.take_profit_triggered or stage2.trailing_stop_triggered:
            logger.info(
                "%s Stage 2 exit signal: %s", settings.log_tag, stage2.message
            )
            self._executor.close_position(settings.TRADING_SYMBOL)
            self._signal_converter.notify_position_closed()
            self._risk_engine.reset_trailing_stop()

        # ---- Step 9: Update metrics + Telegram --------------------------
        self._metrics.record_candle(
            candle_ts=str(candle_ts),
            price=current_price,
            balance=balance.get("available", 0.0),
            unrealized_pnl=pos_updated.get("unrealized_pnl", 0.0),
        )
        self._metrics.record_signal(
            z_score=signal.z_score,
            direction=signal.direction,
            prediction=prediction,
        )
        self._metrics.record_position(
            side=pos_updated.get("side") or "FLAT",
            size=pos_updated.get("size", 0.0),
            entry_price=pos_updated.get("entry_price", 0.0),
            liquidation_price=pos_updated.get("liquidation_price", 0.0),
            leverage=settings.LEVERAGE,
        )
        self._risk_engine.tick_candle()
        logger.info("%s === Trading cycle complete ===", settings.log_tag)

    # ------------------------------------------------------------------
    # Order execution helper
    # ------------------------------------------------------------------

    def _execute_intent(self, intent: Any, current_price: float) -> None:
        """Execute an OrderIntent via the order manager."""
        try:
            if intent.close_size > 0:
                logger.info(
                    "%s Closing %.4f %s",
                    settings.log_tag,
                    intent.close_size,
                    settings.TRADING_SYMBOL,
                )
                self._executor.close_position(settings.TRADING_SYMBOL)

            if intent.open_size > 0 and intent.open_side:
                logger.info(
                    "%s Opening %s %.4f @ ~%.2f",
                    settings.log_tag,
                    intent.open_side,
                    intent.open_size,
                    current_price,
                )
                self._order_manager.submit_market_order(
                    symbol=settings.TRADING_SYMBOL,
                    side=intent.open_side,
                    amount=intent.open_size,
                    intended_price=current_price,
                )
        except Exception as exc:
            logger.error("%s Order execution error: %s", settings.log_tag, exc)
            self._telegram.send_raw(f"Order execution error: {exc}")

    def _reduce_position(self, fraction: float) -> None:
        """Reduce open position by the given fraction (0-1)."""
        try:
            pos = self._executor.get_position(settings.TRADING_SYMBOL)
            size = pos.get("size", 0.0)
            if size > 0:
                reduce_amount = size * fraction
                close_side = "sell" if pos.get("side") == "long" else "buy"
                self._order_manager.submit_market_order(
                    symbol=settings.TRADING_SYMBOL,
                    side=close_side,
                    amount=reduce_amount,
                )
        except Exception as exc:
            logger.error("%s Position reduce error: %s", settings.log_tag, exc)

    # ------------------------------------------------------------------
    # Periodic jobs
    # ------------------------------------------------------------------

    def _fetch_latest_candle(self) -> dict | None:
        """Fetch the most recent closed candle from storage."""
        try:
            df = self._storage.get_recent_candles(limit=1)
            if df is not None and not df.empty:
                row = df.iloc[-1]
                return row.to_dict()
        except Exception as exc:
            logger.error("%s Failed to fetch latest candle: %s", settings.log_tag, exc)
        return None

    def _retrain_models(self) -> None:
        """Weekly model retraining."""
        logger.info("%s Starting weekly model retrain...", settings.log_tag)
        try:
            self._trainer.retrain_rolling()
            self._ensemble.load("models/saved/ensemble.pkl")
            logger.info("%s Model retrain complete.", settings.log_tag)
            self._telegram.send_raw("Weekly model retrain completed successfully.")
        except Exception as exc:
            logger.error("%s Model retrain failed: %s", settings.log_tag, exc)
            self._telegram.send_raw(f"Model retrain FAILED: {exc}")

    def _check_funding_rate(self) -> None:
        """Fetch current funding rate and log cost."""
        try:
            data = self._executor.get_funding_rate(settings.TRADING_SYMBOL)
            rate = data.get("funding_rate", 0.0)
            self._current_funding_rate = rate
            logger.info("%s Funding rate: %.6f%%", settings.log_tag, rate * 100)

            from monitor.metrics import collector
            collector.update(funding_rate=rate)

            if abs(rate) >= 0.001:  # 0.1% threshold
                self._telegram.alert_funding_rate(rate, settings.TRADING_SYMBOL)
        except Exception as exc:
            logger.error("%s Funding rate check failed: %s", settings.log_tag, exc)

    def _health_check(self) -> None:
        """Hourly health check: exchange API, balance, open orders, liquidation."""
        try:
            balance = self._executor.get_balance()
            open_orders = self._order_manager.get_open_orders()
            pos = self._executor.get_position(settings.TRADING_SYMBOL)

            status = {
                "healthy": True,
                "exchange_ok": True,
                "balance_usdt": balance.get("total", 0.0),
                "open_orders": len(open_orders),
                "position_side": pos.get("side", "FLAT"),
                "liquidation_price": pos.get("liquidation_price", 0.0),
            }

            # Warn if close to liquidation
            if pos.get("side") and pos.get("liquidation_price", 0):
                current = self._metrics.snapshot().get("current_price", 0)
                liq = pos["liquidation_price"]
                if current and liq:
                    proximity = abs(current - liq) / abs(pos.get("entry_price", current) - liq + 1e-9)
                    if proximity < 0.3:
                        self._telegram.warn_liquidation_proximity(
                            (1 - proximity) * 100,
                            current,
                            liq,
                            "Monitor closely",
                        )

            logger.info("%s Health check: %s", settings.log_tag, status)
            self._telegram.notify_health_check(status)
        except Exception as exc:
            logger.error("%s Health check failed: %s", settings.log_tag, exc)
            if self._telegram:
                self._telegram.send_raw(f"Health check FAILED: {exc}")

    def _send_daily_report(self) -> None:
        """Daily report at 00:00 UTC."""
        try:
            metrics = self._metrics.snapshot()
            self._telegram.send_daily_report(
                date_str=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                total_trades=metrics.get("total_trades", 0),
                win_rate=metrics.get("win_rate", 0.0),
                daily_pnl_pct=metrics.get("daily_pnl_pct", 0.0),
                total_pnl_pct=metrics.get("total_pnl_pct", 0.0),
                max_drawdown_pct=metrics.get("drawdown_pct", 0.0),
                balance_usdt=metrics.get("balance_usdt", 0.0),
            )
        except Exception as exc:
            logger.error("%s Daily report failed: %s", settings.log_tag, exc)

    # ------------------------------------------------------------------
    # Control API (called by FastAPI routes)
    # ------------------------------------------------------------------

    def set_leverage(self, leverage: int) -> None:
        """Dynamically update leverage (applies to new positions)."""
        if leverage < 1 or leverage > 10:
            raise ValueError(f"Leverage must be 1-10, got {leverage}")
        self._executor.initialize_futures(
            settings.TRADING_SYMBOL, leverage, settings.MARGIN_TYPE
        )
        logger.info("%s Leverage updated to %dx", settings.log_tag, leverage)
