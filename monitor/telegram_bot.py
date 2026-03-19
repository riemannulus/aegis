"""Telegram notification bot for Aegis.

Auto-tags messages with [TESTNET] or [🔴 MAINNET] based on USE_TESTNET setting.
Sends trade alerts, daily reports, risk warnings, and system messages.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from config.settings import settings

logger = logging.getLogger(__name__)


def _send(text: str) -> None:
    """Send a Telegram message. No-op if token/chat_id not configured."""
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        logger.debug("Telegram not configured — message suppressed: %s", text[:80])
        return
    try:
        import requests  # lazy import
        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": settings.TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
        }
        resp = requests.post(url, json=payload, timeout=10)
        if not resp.ok:
            logger.warning("Telegram send failed: %s %s", resp.status_code, resp.text[:200])
    except Exception as exc:
        logger.error("Telegram error: %s", exc)


def _tag() -> str:
    """Return env tag for message prefix."""
    if settings.USE_TESTNET:
        return "[TESTNET]"
    return "[🔴 MAINNET]"


class TelegramBot:
    """High-level Telegram notification interface for Aegis."""

    # ------------------------------------------------------------------
    # Trade notifications
    # ------------------------------------------------------------------

    def notify_trade_open(
        self,
        direction: str,
        symbol: str,
        price: float,
        size: float,
        leverage: int,
        z_score: float,
        liquidation_price: float,
    ) -> None:
        """Send trade open notification.

        Format: {tag}[LONG 3x] BTC/USDT @ 65,000 | Size: 0.01 BTC | Signal Z: 2.1 | Liq: 58,200
        """
        msg = (
            f"{_tag()}[{direction.upper()} {leverage}x] {symbol} @ {price:,.0f}\n"
            f"Size: {size:.4f} BTC | Signal Z: {z_score:.2f} | Liq: {liquidation_price:,.0f}"
        )
        _send(msg)

    def notify_trade_close(
        self,
        direction: str,
        symbol: str,
        pnl_pct: float,
        funding_cost_usdt: float,
        hold_hours: float,
        reason: str = "",
    ) -> None:
        """Send trade close notification.

        Format: {tag}[CLOSE LONG] BTC/USDT | PnL: +3.6% (lev) | Funding: -$1.20 | Hold: 3h
        """
        sign = "+" if pnl_pct >= 0 else ""
        msg = (
            f"{_tag()}[CLOSE {direction.upper()}] {symbol}\n"
            f"PnL: {sign}{pnl_pct:.2f}% (lev) | Funding: -${abs(funding_cost_usdt):.2f} | "
            f"Hold: {hold_hours:.1f}h"
        )
        if reason:
            msg += f"\nReason: {reason}"
        _send(msg)

    # ------------------------------------------------------------------
    # Risk warnings
    # ------------------------------------------------------------------

    def warn_drawdown(self, drawdown_pct: float, action: str) -> None:
        msg = (
            f"⚠️ {_tag()} DRAWDOWN ALERT\n"
            f"Current drawdown: {drawdown_pct:.2f}%\n"
            f"Action: {action}"
        )
        _send(msg)

    def warn_liquidation_proximity(
        self,
        proximity_pct: float,
        current_price: float,
        liquidation_price: float,
        action: str,
    ) -> None:
        msg = (
            f"🚨 {_tag()} LIQUIDATION WARNING\n"
            f"Proximity: {proximity_pct:.0f}% of way to liquidation\n"
            f"Current: {current_price:,.0f} | Liq: {liquidation_price:,.0f}\n"
            f"Action: {action}"
        )
        _send(msg)

    def alert_emergency(self, reason: str) -> None:
        msg = f"🚨🚨 {_tag()} EMERGENCY CLOSE\n{reason}"
        _send(msg)

    def alert_funding_rate(self, funding_rate: float, symbol: str) -> None:
        msg = (
            f"⚠️ {_tag()} High Funding Rate\n"
            f"{symbol}: {funding_rate*100:.4f}%"
        )
        _send(msg)

    # ------------------------------------------------------------------
    # Daily report
    # ------------------------------------------------------------------

    def send_daily_report(
        self,
        date_str: str,
        total_trades: int,
        win_rate: float,
        daily_pnl_pct: float,
        total_pnl_pct: float,
        max_drawdown_pct: float,
        balance_usdt: float,
    ) -> None:
        sign = "+" if daily_pnl_pct >= 0 else ""
        msg = (
            f"📊 {_tag()} Daily Report — {date_str}\n"
            f"Trades: {total_trades} | Win rate: {win_rate*100:.1f}%\n"
            f"Daily PnL: {sign}{daily_pnl_pct:.2f}% | Total PnL: {'+' if total_pnl_pct>=0 else ''}{total_pnl_pct:.2f}%\n"
            f"Max drawdown: {max_drawdown_pct:.2f}%\n"
            f"Balance: {balance_usdt:,.2f} USDT"
        )
        _send(msg)

    # ------------------------------------------------------------------
    # System messages
    # ------------------------------------------------------------------

    def notify_system_start(self) -> None:
        if settings.USE_TESTNET:
            msg = f"{_tag()} Aegis trading system started (Testnet mode)"
        else:
            msg = (
                f"{_tag()} ⚠️ Aegis trading system started on MAINNET\n"
                f"Real funds at risk. Monitor closely."
            )
        _send(msg)

    def notify_system_stop(self, reason: str = "Manual stop") -> None:
        msg = f"{_tag()} Aegis trading system stopped\nReason: {reason}"
        _send(msg)

    def notify_health_check(self, status: dict[str, Any]) -> None:
        ok = "✅" if status.get("healthy") else "❌"
        msg = (
            f"{ok} {_tag()} Health Check\n"
            f"Exchange: {'✅' if status.get('exchange_ok') else '❌'} | "
            f"Balance: {status.get('balance_usdt', 0):.2f} USDT | "
            f"Open orders: {status.get('open_orders', 0)}"
        )
        _send(msg)

    def send_raw(self, text: str) -> None:
        """Send arbitrary text (prefixed with env tag)."""
        _send(f"{_tag()} {text}")


# Module-level singleton
bot = TelegramBot()
