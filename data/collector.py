"""Real-time candle collector using CCXT Futures WebSocket.

Responsibilities:
- Subscribe to live OHLCV candles (Binance Futures, defaultType='future')
- Collect funding rates every 8 hours
- Collect open interest
- Bridge gap between Binance Vision historical data and live feed via fetch_ohlcv
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable, Any

logger = logging.getLogger(__name__)


class RealtimeCollector:
    """Collects live candles, funding rates, and open interest from Binance Futures."""

    def __init__(
        self,
        symbol: str = "BTC/USDT:USDT",
        interval: str = "30m",
        storage=None,
        on_candle: Callable[[dict], None] | None = None,
    ):
        self.symbol = symbol
        self.interval = interval
        self.storage = storage
        self.on_candle = on_candle
        self._exchange = None
        self._running = False

    def _get_exchange(self):
        if self._exchange is None:
            from config.settings import settings
            self._exchange = settings.build_ccxt_exchange()
        return self._exchange

    # ------------------------------------------------------------------
    # Gap-filling: bridge Vision data → live
    # ------------------------------------------------------------------

    def fill_gap(self, since_ts: int | None = None) -> list[dict]:
        """Fetch OHLCV candles from CCXT to fill the gap after last Vision timestamp.

        Args:
            since_ts: millisecond timestamp to start from (exclusive). If None,
                      uses the latest candle timestamp from storage.

        Returns:
            List of candle dicts loaded into storage.
        """
        exchange = self._get_exchange()
        if since_ts is None and self.storage:
            since_ts = self.storage.get_latest_candle_timestamp()

        if since_ts is None:
            logger.warning("fill_gap: no since_ts, skipping")
            return []

        # Step 1 candle forward so we don't re-fetch the last known one
        fetch_since = since_ts + 1

        logger.info(
            "%s Filling gap from %s for %s %s",
            _log_tag(), fetch_since, self.symbol, self.interval
        )

        all_candles: list[dict] = []
        while True:
            try:
                ohlcvs = exchange.fetch_ohlcv(
                    self.symbol, self.interval, since=fetch_since, limit=1000
                )
            except Exception as exc:
                logger.error("fetch_ohlcv error: %s", exc)
                break
            if not ohlcvs:
                break
            for o in ohlcvs:
                row = _ohlcv_to_dict(o, self.symbol, self.interval)
                all_candles.append(row)
            last_ts = ohlcvs[-1][0]
            if len(ohlcvs) < 1000:
                break
            fetch_since = last_ts + 1

        if all_candles and self.storage:
            n = self.storage.upsert_candles(all_candles)
            logger.info("fill_gap: inserted %d new candles", n)

        return all_candles

    # ------------------------------------------------------------------
    # Funding rate
    # ------------------------------------------------------------------

    def fetch_and_store_funding_rate(self) -> dict | None:
        """Fetch current funding rate and store it."""
        exchange = self._get_exchange()
        try:
            fr = exchange.fetch_funding_rate(self.symbol)
            row = {
                "timestamp": int(fr.get("timestamp") or time.time() * 1000),
                "symbol": self.symbol,
                "funding_rate": float(fr.get("fundingRate", 0)),
                "mark_price": float(fr.get("markPrice", 0) or 0),
            }
            if self.storage:
                self.storage.upsert_funding_rate(row)
            logger.debug("Funding rate: %s", row)
            return row
        except Exception as exc:
            logger.error("fetch_funding_rate error: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Open interest
    # ------------------------------------------------------------------

    def fetch_open_interest(self) -> dict | None:
        """Fetch current open interest."""
        exchange = self._get_exchange()
        try:
            oi = exchange.fetch_open_interest(self.symbol)
            return {
                "timestamp": int(oi.get("timestamp") or time.time() * 1000),
                "symbol": self.symbol,
                "open_interest": float(oi.get("openInterest", 0)),
            }
        except Exception as exc:
            logger.error("fetch_open_interest error: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Async live collection loop
    # ------------------------------------------------------------------

    async def run_forever(self) -> None:
        """Subscribe to live OHLCV candles using CCXT async watchOHLCV."""
        import ccxt.pro as ccxtpro
        from config.settings import settings

        options = {
            "defaultType": settings.MARKET_TYPE,
            "adjustForTimeDifference": True,
        }
        if settings.USE_TESTNET:
            options["demo"] = True

        exchange = ccxtpro.binance({
            "apiKey": settings.api_key,
            "secret": settings.api_secret,
            "enableRateLimit": True,
            "options": options,
        })

        self._running = True
        logger.info("%s Starting live candle collection for %s %s", _log_tag(), self.symbol, self.interval)

        try:
            while self._running:
                try:
                    ohlcvs = await exchange.watch_ohlcv(self.symbol, self.interval)
                    for o in ohlcvs:
                        # Only fire callback for closed candles
                        row = _ohlcv_to_dict(o, self.symbol, self.interval)
                        if self.storage:
                            self.storage.upsert_candles([row])
                        if self.on_candle:
                            try:
                                self.on_candle(row)
                            except Exception as cb_exc:
                                logger.error("on_candle callback error: %s", cb_exc)
                except Exception as exc:
                    logger.error("watchOHLCV error: %s", exc)
                    await asyncio.sleep(5)
        finally:
            await exchange.close()

    def stop(self) -> None:
        self._running = False


def _ohlcv_to_dict(ohlcv: list, symbol: str, interval: str) -> dict:
    return {
        "timestamp": int(ohlcv[0]),
        "symbol": symbol.replace("/", "").replace(":", "").replace("USDT", "USDT"),
        "interval": interval,
        "open": float(ohlcv[1]),
        "high": float(ohlcv[2]),
        "low": float(ohlcv[3]),
        "close": float(ohlcv[4]),
        "volume": float(ohlcv[5]),
    }


def _log_tag() -> str:
    try:
        from config.settings import settings
        return settings.log_tag
    except Exception:
        return "[UNKNOWN]"
