#!/usr/bin/env python3
"""CLI script to download Binance Vision historical futures data and load into storage.

Usage:
    python scripts/download_binance_vision.py --symbol BTCUSDT --interval 30m \\
        --start 2024-01-01 --end 2025-03-01
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime

# Ensure project root is on path
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.binance_vision import download_range, to_storage_rows
from data.storage import Storage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download Binance Vision futures kline data and store in SQLite"
    )
    parser.add_argument("--symbol", default="BTCUSDT", help="Binance Vision symbol (e.g. BTCUSDT)")
    parser.add_argument("--interval", default="30m", help="Kline interval (30m, 1h, ...)")
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--db", default="data/aegis.db", help="SQLite database path")
    parser.add_argument("--no-checksum", action="store_true", help="Skip SHA256 checksum verification")
    args = parser.parse_args()

    start = parse_date(args.start)
    end = parse_date(args.end)

    if start > end:
        logger.error("--start must be before --end")
        sys.exit(1)

    logger.info("Downloading %s %s from %s to %s", args.symbol, args.interval, start, end)

    df = download_range(
        symbol=args.symbol,
        interval=args.interval,
        start=start,
        end=end,
        verify_checksum=not args.no_checksum,
    )

    if df.empty:
        logger.error("No data downloaded. Check symbol/interval/date range.")
        sys.exit(1)

    # Load into storage
    storage = Storage(db_path=args.db)
    rows = to_storage_rows(df, symbol=args.symbol, interval=args.interval)
    inserted = storage.upsert_candles(rows)

    # Integrity report
    total = len(df)
    start_ts = int(df["open_time"].iloc[0])
    end_ts = int(df["open_time"].iloc[-1])
    start_dt = datetime.utcfromtimestamp(start_ts / 1000).strftime("%Y-%m-%d %H:%M")
    end_dt = datetime.utcfromtimestamp(end_ts / 1000).strftime("%Y-%m-%d %H:%M")

    # Check for gaps
    interval_ms = _interval_to_ms(args.interval)
    timestamps = df["open_time"].astype(int).tolist()
    gaps = []
    for i in range(1, len(timestamps)):
        diff = timestamps[i] - timestamps[i - 1]
        if diff > interval_ms * 1.5:
            gap_start = datetime.utcfromtimestamp(timestamps[i - 1] / 1000).strftime("%Y-%m-%d %H:%M")
            gap_end = datetime.utcfromtimestamp(timestamps[i] / 1000).strftime("%Y-%m-%d %H:%M")
            gaps.append(f"  {gap_start} → {gap_end} ({diff // interval_ms - 1} missing candles)")

    print("\n" + "=" * 60)
    print("DOWNLOAD INTEGRITY REPORT")
    print("=" * 60)
    print(f"Symbol:       {args.symbol}")
    print(f"Interval:     {args.interval}")
    print(f"Total candles: {total:,}")
    print(f"Date range:   {start_dt} UTC → {end_dt} UTC")
    print(f"Newly inserted: {inserted:,}")
    if gaps:
        print(f"Missing gaps ({len(gaps)}):")
        for g in gaps[:10]:
            print(g)
        if len(gaps) > 10:
            print(f"  ... and {len(gaps) - 10} more")
    else:
        print("Gaps:         None (data is continuous)")
    print("=" * 60)


def _interval_to_ms(interval: str) -> int:
    units = {"m": 60_000, "h": 3_600_000, "d": 86_400_000}
    unit = interval[-1]
    num = int(interval[:-1])
    return num * units.get(unit, 60_000)


if __name__ == "__main__":
    main()
