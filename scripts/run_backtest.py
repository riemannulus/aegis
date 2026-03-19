#!/usr/bin/env python
"""Run Aegis backtest against historical Futures data.

⚠️  All backtesting uses USE_TESTNET=True.  This script NEVER touches Mainnet.

Usage:
    python scripts/run_backtest.py [--symbol BTCUSDT] [--interval 30m]
                                   [--start 2024-01-01] [--end 2025-01-01]
                                   [--leverage 3] [--capital 10000]
                                   [--output results/backtest_YYYYMMDD.json]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("run_backtest")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Aegis Futures backtest (Testnet data only)")
    p.add_argument("--symbol", default="BTCUSDT")
    p.add_argument("--interval", default=settings.TIMEFRAME)
    p.add_argument("--start", default="2024-01-01", help="Start date YYYY-MM-DD")
    p.add_argument("--end", default="2025-01-01", help="End date YYYY-MM-DD")
    p.add_argument("--leverage", type=int, default=settings.LEVERAGE)
    p.add_argument("--capital", type=float, default=10_000.0, help="Initial capital (USDT)")
    p.add_argument("--model-dir", default="models/saved")
    p.add_argument("--output", default="", help="Path to save JSON results (optional)")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    # Safety guard — backtest must always run against Testnet data
    if not settings.USE_TESTNET:
        logger.warning(
            "USE_TESTNET=False detected. Backtest is forced to run in paper mode only. "
            "No live orders will be placed."
        )

    logger.info("%s Starting backtest", settings.log_tag)
    logger.info(
        "Symbol=%s  Interval=%s  Period=%s→%s  Leverage=%dx  Capital=%.2f USDT",
        args.symbol, args.interval, args.start, args.end,
        args.leverage, args.capital,
    )

    # ------------------------------------------------------------------
    # 1. Load historical data
    # ------------------------------------------------------------------
    from data.storage import Storage
    from data.feature_engineer import FeatureEngineer

    storage = Storage()
    logger.info("Loading candle data for %s → %s …", args.start, args.end)
    candles = storage.get_candles_range(
        symbol=args.symbol,
        interval=args.interval,
        start=args.start,
        end=args.end,
    )
    if not candles or len(candles) == 0:
        logger.error(
            "No candle data in DB for the requested period. "
            "Run scripts/download_binance_vision.py first."
        )
        sys.exit(1)

    logger.info("Loaded %d candles", len(candles))

    fe = FeatureEngineer()
    features_df = fe.compute(candles)

    # ------------------------------------------------------------------
    # 2. Load models
    # ------------------------------------------------------------------
    from models.trainer import ModelTrainer

    model_dir = Path(args.model_dir)
    if not model_dir.exists():
        logger.error("Model directory %s does not exist. Train models first.", model_dir)
        sys.exit(1)

    trainer = ModelTrainer(save_dir=str(model_dir))
    trainer.load_all_models()
    logger.info("Models loaded from %s", model_dir)

    # ------------------------------------------------------------------
    # 3. Run backtest loop using PaperTrader
    # ------------------------------------------------------------------
    from execution.paper_trader import PaperTrader
    from strategy.signal_converter import SignalConverter
    from strategy.position_manager import PositionManager
    from strategy.regime_detector import RegimeDetector
    from strategy.decision_logger import DecisionLogger, MarketSnapshot, ModelPredictions, SignalInfo, RiskCheckInfo
    from risk.risk_engine import RiskEngine

    paper = PaperTrader(initial_balance=args.capital, leverage=args.leverage)
    signal_conv = SignalConverter()
    pos_mgr = PositionManager()
    regime_det = RegimeDetector()
    risk_eng = RiskEngine()
    risk_eng.initialise(opening_balance=args.capital)
    dl = DecisionLogger(storage=None)   # no DB during backtest

    trades = []
    decisions = []
    equity_curve = []

    logger.info("Running backtest loop over %d candles …", len(features_df))

    for i, (ts, row) in enumerate(features_df.iterrows()):
        try:
            # Predict
            X = row.values.reshape(1, -1)
            preds = trainer.predict_all(X)
            ensemble_pred = preds.get("ensemble", 0.0)

            # Regime
            router_weights = preds.get("tra_router_weights", [0.33, 0.33, 0.34])
            regime_result = regime_det.detect(router_weights)
            risk_eng.set_regime_params(regime_result.params)

            # Signal
            sig = signal_conv.convert(ensemble_pred)

            # Current paper state
            balance = paper.get_balance()
            pos = paper.get_position()
            equity = balance + (pos.get("unrealized_pnl", 0.0) if pos else 0.0)
            equity_curve.append({"timestamp": str(ts), "equity": equity})

            candle_price = float(row.get("close", 0.0))

            # Stage 1 risk check
            order_usdt = balance * sig.size_ratio * settings.MAX_POSITION_RATIO
            stage1 = risk_eng.check_pre_order(
                order_usdt=order_usdt,
                account_balance=balance,
            )

            if sig.direction == "FLAT" or not stage1.passed:
                decision_type = "SKIP" if sig.direction == "FLAT" else "REJECTED_BY_RISK"
                reason = (
                    DecisionLogger.build_skip_reason(sig.z_score, settings.MIN_SIGNAL_THRESHOLD)
                    if sig.direction == "FLAT"
                    else DecisionLogger.build_rejected_reason(stage1.reason)
                )
            else:
                decision_type = "EXECUTE"
                reason = DecisionLogger.build_execute_reason(
                    sig.z_score, sig.direction, regime_result.regime, sig.size_ratio
                )
                # Execute on paper trader
                side = "buy" if sig.direction == "LONG" else "sell"
                paper.create_market_order(
                    symbol=args.symbol,
                    side=side,
                    amount=order_usdt / candle_price if candle_price > 0 else 0.0,
                )

            decisions.append({
                "timestamp": str(ts),
                "decision": decision_type,
                "direction": sig.direction,
                "z_score": round(sig.z_score, 4),
                "regime": regime_result.regime,
                "reason": reason,
            })

            risk_eng.tick_candle()

        except Exception as exc:
            logger.warning("Candle %d error: %s", i, exc)
            continue

    # ------------------------------------------------------------------
    # 4. Compute performance metrics
    # ------------------------------------------------------------------
    from analytics.pnl_calculator import PnLCalculator
    from analytics.performance_metrics import PerformanceMetrics

    paper_trades = paper.get_trade_history()
    pnl_calc = PnLCalculator()
    perf = PerformanceMetrics()

    final_balance = paper.get_balance()
    total_return = (final_balance - args.capital) / args.capital

    logger.info("--- Backtest Results ---")
    logger.info("Period:         %s → %s", args.start, args.end)
    logger.info("Initial capital: %.2f USDT", args.capital)
    logger.info("Final balance:   %.2f USDT", final_balance)
    logger.info("Total return:    %.2f%%", total_return * 100)
    logger.info("Total trades:    %d", len(paper_trades))
    logger.info("Total decisions: %d", len(decisions))

    results = {
        "backtest_params": {
            "symbol": args.symbol,
            "interval": args.interval,
            "start": args.start,
            "end": args.end,
            "leverage": args.leverage,
            "initial_capital": args.capital,
        },
        "summary": {
            "final_balance": final_balance,
            "total_return_pct": round(total_return * 100, 4),
            "total_trades": len(paper_trades),
            "total_decisions": len(decisions),
        },
        "equity_curve": equity_curve[-200:],   # last 200 points in JSON output
        "decisions_sample": decisions[:50],
    }

    # ------------------------------------------------------------------
    # 5. Save results
    # ------------------------------------------------------------------
    output_path = args.output
    if not output_path:
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        results_dir = Path("results")
        results_dir.mkdir(exist_ok=True)
        output_path = str(results_dir / f"backtest_{ts_str}.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    logger.info("%s Backtest complete. Results saved to %s", settings.log_tag, output_path)


if __name__ == "__main__":
    main()
