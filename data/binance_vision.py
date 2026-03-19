"""Binance Vision historical data downloader.

Downloads USDS-M Futures kline data from https://data.binance.vision
Uses monthly ZIP archives with SHA256 checksum verification.
Caches downloaded ZIPs in data/raw/ to avoid re-downloads.
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import time
import zipfile
from datetime import date, timedelta
from pathlib import Path
from typing import Generator

import pandas as pd
import requests
from tqdm import tqdm

logger = logging.getLogger(__name__)

BASE_URL = "https://data.binance.vision"
RAW_DIR = Path("data/raw")

KLINE_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_volume", "count",
    "taker_buy_volume", "taker_buy_quote_volume", "ignore",
]


def _monthly_url(symbol: str, interval: str, year: int, month: int) -> str:
    fname = f"{symbol}-{interval}-{year}-{month:02d}.zip"
    return f"{BASE_URL}/data/futures/um/monthly/klines/{symbol}/{interval}/{fname}"


def _daily_url(symbol: str, interval: str, year: int, month: int, day: int) -> str:
    fname = f"{symbol}-{interval}-{year}-{month:02d}-{day:02d}.zip"
    return f"{BASE_URL}/data/futures/um/daily/klines/{symbol}/{interval}/{fname}"


def _checksum_url(data_url: str) -> str:
    return data_url + ".CHECKSUM"


def _months_in_range(start: date, end: date) -> Generator[tuple[int, int], None, None]:
    current = date(start.year, start.month, 1)
    while current <= date(end.year, end.month, 1):
        yield current.year, current.month
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)


def _download_with_retry(url: str, max_retries: int = 3) -> bytes | None:
    """Download URL content with exponential backoff. Returns None if not found."""
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, timeout=60, stream=True)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.content
        except requests.RequestException as exc:
            if attempt == max_retries - 1:
                logger.warning("Failed to download %s after %d attempts: %s", url, max_retries, exc)
                return None
            wait = 2 ** attempt
            logger.debug("Retry %d/%d for %s in %ds", attempt + 1, max_retries, url, wait)
            time.sleep(wait)
    return None


def _verify_checksum(data: bytes, checksum_content: str) -> bool:
    expected = checksum_content.strip().split()[0].lower()
    actual = hashlib.sha256(data).hexdigest().lower()
    return expected == actual


def _parse_zip(zip_bytes: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        csv_name = next(n for n in zf.namelist() if n.endswith(".csv"))
        with zf.open(csv_name) as f:
            df = pd.read_csv(f, header=None, names=KLINE_COLUMNS)
    df["open_time"] = pd.to_numeric(df["open_time"], errors="coerce")
    for col in ["open", "high", "low", "close", "volume", "quote_volume",
                "taker_buy_volume", "taker_buy_quote_volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["count"] = pd.to_numeric(df["count"], errors="coerce").astype("Int64")
    df.drop(columns=["ignore"], inplace=True, errors="ignore")
    return df


def _cache_path(url: str) -> Path:
    fname = url.split("/")[-1]
    return RAW_DIR / fname


def download_monthly(
    symbol: str,
    interval: str,
    start: date,
    end: date,
    verify_checksum: bool = True,
) -> pd.DataFrame:
    """Download monthly kline ZIPs from Binance Vision for a date range.

    Args:
        symbol: Binance Vision symbol, e.g. 'BTCUSDT' (no slash)
        interval: '30m' or '1h'
        start: inclusive start date
        end: inclusive end date
        verify_checksum: verify SHA256 checksums

    Returns:
        DataFrame with columns: open_time, open, high, low, close, volume, ...
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    frames: list[pd.DataFrame] = []
    months = list(_months_in_range(start, end))

    for year, month in tqdm(months, desc=f"Downloading {symbol} {interval}"):
        url = _monthly_url(symbol, interval, year, month)
        cache = _cache_path(url)

        if cache.exists():
            logger.debug("Cache hit: %s", cache)
            zip_bytes = cache.read_bytes()
        else:
            zip_bytes = _download_with_retry(url)
            if zip_bytes is None:
                logger.warning("Skipping missing: %s", url)
                continue
            if verify_checksum:
                cs_content = _download_with_retry(_checksum_url(url))
                if cs_content:
                    if not _verify_checksum(zip_bytes, cs_content.decode()):
                        logger.error("Checksum mismatch for %s — skipping", url)
                        continue
                    logger.debug("Checksum OK: %s", url)
            cache.write_bytes(zip_bytes)

        try:
            df = _parse_zip(zip_bytes)
            frames.append(df)
        except Exception as exc:
            logger.error("Failed to parse %s: %s", url, exc)

    if not frames:
        return pd.DataFrame(columns=KLINE_COLUMNS[:-1])

    result = pd.concat(frames, ignore_index=True)
    result.sort_values("open_time", inplace=True)
    result.drop_duplicates(subset=["open_time"], inplace=True)
    result.reset_index(drop=True, inplace=True)
    return result


def download_range(
    symbol: str,
    interval: str,
    start: date,
    end: date,
    verify_checksum: bool = True,
) -> pd.DataFrame:
    """Download kline data for a date range (monthly archives only).

    For the current/incomplete month, falls back to daily archives.
    """
    today = date.today()
    # Use monthly for completed months, daily for current month
    monthly_end = date(today.year, today.month, 1) - timedelta(days=1)
    effective_end = min(end, monthly_end)

    frames: list[pd.DataFrame] = []

    if start <= effective_end:
        df_monthly = download_monthly(symbol, interval, start, effective_end, verify_checksum)
        if not df_monthly.empty:
            frames.append(df_monthly)

    # Fill current partial month with daily files if needed
    if end > monthly_end:
        daily_start = max(start, date(today.year, today.month, 1))
        d = daily_start
        while d <= end:
            url = _daily_url(symbol, interval, d.year, d.month, d.day)
            cache = _cache_path(url)
            if cache.exists():
                zip_bytes = cache.read_bytes()
            else:
                zip_bytes = _download_with_retry(url)
                if zip_bytes is None:
                    d += timedelta(days=1)
                    continue
                cache.write_bytes(zip_bytes)
            try:
                frames.append(_parse_zip(zip_bytes))
            except Exception as exc:
                logger.error("Failed to parse daily %s: %s", url, exc)
            d += timedelta(days=1)

    if not frames:
        return pd.DataFrame(columns=KLINE_COLUMNS[:-1])

    result = pd.concat(frames, ignore_index=True)
    result.sort_values("open_time", inplace=True)
    result.drop_duplicates(subset=["open_time"], inplace=True)
    result.reset_index(drop=True, inplace=True)
    return result


def to_storage_rows(df: pd.DataFrame, symbol: str = "BTCUSDT", interval: str = "30m") -> list[dict]:
    """Convert a Binance Vision DataFrame into storage.Candle dicts."""
    rows = []
    for _, row in df.iterrows():
        rows.append({
            "timestamp": int(row["open_time"]),
            "symbol": symbol,
            "interval": interval,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
            "quote_volume": float(row.get("quote_volume", 0) or 0),
            "count": int(row.get("count", 0) or 0),
            "taker_buy_volume": float(row.get("taker_buy_volume", 0) or 0),
            "taker_buy_quote_volume": float(row.get("taker_buy_quote_volume", 0) or 0),
        })
    return rows
