"""Binance Futures WebSocket real-time data feed.

Subscribes to:
- OHLCV klines via CCXT watchOHLCV (defaultType='future')
- btcusdt@markPrice (mark price + funding rate)
- btcusdt@forceOrder (liquidation events)

Features:
- Reconnection with exponential backoff (max 5 retries)
- Heartbeat check every 30s
- Fires on_candle callback when a candle closes
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Callable, Any

import websockets

logger = logging.getLogger(__name__)

FSTREAM_BASE = "wss://fstream.binance.com/ws"
TESTNET_FSTREAM_BASE = "wss://stream.binancefuture.com/ws"

MAX_RETRIES = 5
HEARTBEAT_INTERVAL = 30  # seconds


class RealtimeFeed:
    """Manages Binance Futures WebSocket streams for real-time data."""

    def __init__(
        self,
        symbol: str = "BTC/USDT:USDT",
        interval: str = "30m",
        on_candle: Callable[[dict], None] | None = None,
        on_mark_price: Callable[[dict], None] | None = None,
        on_liquidation: Callable[[dict], None] | None = None,
        use_testnet: bool = True,
    ):
        self.symbol = symbol
        self.interval = interval
        self.on_candle = on_candle
        self.on_mark_price = on_mark_price
        self.on_liquidation = on_liquidation
        self.use_testnet = use_testnet
        self._running = False
        self._last_heartbeat = time.time()

        # Derive Binance stream symbol (lowercase, no special chars)
        self._stream_symbol = symbol.replace("/", "").replace(":", "").replace("USDT", "usdt").lower()
        # e.g. BTC/USDT:USDT → btcusdt
        if "btc" in self._stream_symbol:
            self._stream_symbol = "btcusdt"

    @property
    def _base_url(self) -> str:
        return TESTNET_FSTREAM_BASE if self.use_testnet else FSTREAM_BASE

    def _kline_stream_url(self) -> str:
        return f"{self._base_url}/{self._stream_symbol}@kline_{self.interval}"

    def _mark_price_url(self) -> str:
        return f"{self._base_url}/{self._stream_symbol}@markPrice"

    def _force_order_url(self) -> str:
        return f"{self._base_url}/{self._stream_symbol}@forceOrder"

    # ------------------------------------------------------------------
    # Combined stream (klines + mark price + liquidations)
    # ------------------------------------------------------------------

    async def run_forever(self) -> None:
        """Start all WebSocket streams and run until stopped."""
        self._running = True
        await asyncio.gather(
            self._run_kline_stream(),
            self._run_mark_price_stream(),
            self._run_force_order_stream(),
            self._heartbeat_loop(),
        )

    def stop(self) -> None:
        self._running = False

    async def _connect_with_retry(self, url: str, handler: Callable) -> None:
        retries = 0
        while self._running:
            try:
                logger.info("Connecting to %s", url)
                async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
                    retries = 0  # reset on successful connection
                    self._last_heartbeat = time.time()
                    async for raw in ws:
                        if not self._running:
                            break
                        self._last_heartbeat = time.time()
                        try:
                            msg = json.loads(raw)
                            handler(msg)
                        except Exception as exc:
                            logger.error("Handler error for %s: %s", url, exc)
            except Exception as exc:
                if not self._running:
                    break
                retries += 1
                if retries > MAX_RETRIES:
                    logger.error("Max retries exceeded for %s, giving up", url)
                    break
                wait = min(2 ** retries, 60)
                logger.warning("WebSocket %s disconnected (%s). Retry %d/%d in %ds",
                               url, exc, retries, MAX_RETRIES, wait)
                await asyncio.sleep(wait)

    async def _run_kline_stream(self) -> None:
        await self._connect_with_retry(self._kline_stream_url(), self._handle_kline)

    async def _run_mark_price_stream(self) -> None:
        await self._connect_with_retry(self._mark_price_url(), self._handle_mark_price)

    async def _run_force_order_stream(self) -> None:
        await self._connect_with_retry(self._force_order_url(), self._handle_force_order)

    async def _heartbeat_loop(self) -> None:
        while self._running:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            elapsed = time.time() - self._last_heartbeat
            if elapsed > HEARTBEAT_INTERVAL * 2:
                logger.warning("Heartbeat timeout: last message %.0fs ago", elapsed)

    # ------------------------------------------------------------------
    # Message handlers
    # ------------------------------------------------------------------

    def _handle_kline(self, msg: dict) -> None:
        k = msg.get("k", {})
        if not k:
            return
        candle = {
            "timestamp": int(k["t"]),
            "symbol": self._stream_symbol.upper(),
            "interval": k.get("i", self.interval),
            "open": float(k["o"]),
            "high": float(k["h"]),
            "low": float(k["l"]),
            "close": float(k["c"]),
            "volume": float(k["v"]),
            "is_closed": bool(k.get("x", False)),
        }
        if candle["is_closed"] and self.on_candle:
            try:
                self.on_candle(candle)
            except Exception as exc:
                logger.error("on_candle callback error: %s", exc)

    def _handle_mark_price(self, msg: dict) -> None:
        if not self.on_mark_price:
            return
        data = {
            "timestamp": int(msg.get("T", time.time() * 1000)),
            "mark_price": float(msg.get("p", 0)),
            "funding_rate": float(msg.get("r", 0)),
            "next_funding_time": int(msg.get("T", 0)),
        }
        try:
            self.on_mark_price(data)
        except Exception as exc:
            logger.error("on_mark_price callback error: %s", exc)

    def _handle_force_order(self, msg: dict) -> None:
        if not self.on_liquidation:
            return
        order = msg.get("o", {})
        data = {
            "timestamp": int(order.get("T", time.time() * 1000)),
            "symbol": order.get("s", ""),
            "side": order.get("S", ""),
            "price": float(order.get("p", 0)),
            "quantity": float(order.get("q", 0)),
            "filled_quantity": float(order.get("l", 0)),
            "average_price": float(order.get("ap", 0)),
        }
        try:
            self.on_liquidation(data)
        except Exception as exc:
            logger.error("on_liquidation callback error: %s", exc)
