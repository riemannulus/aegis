#!/usr/bin/env python3
"""Load already-downloaded Binance Vision ZIP files from data/raw/ into SQLite.

Useful when ZIP files are already cached and you just want to (re-)populate the DB.

Usage:
    python scripts/backfill_data.py --symbol BTCUSDT --interval 30m
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.binance_vision import _parse_zip, to_storage_rows
from data.storage import Storage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

RAW_DIR = Path("data/raw")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill DB from cached Binance Vision ZIP files")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", default="30m")
    parser.add_argument("--db", default="data/aegis.db")
    args = parser.parse_args()

    prefix = f"{args.symbol}-{args.interval}-"
    zips = sorted(RAW_DIR.glob(f"{prefix}*.zip"))

    if not zips:
        logger.error("No ZIP files found in %s matching %s*.zip", RAW_DIR, prefix)
        sys.exit(1)

    logger.info("Found %d ZIP files to backfill", len(zips))
    storage = Storage(db_path=args.db)
    total_inserted = 0

    for zip_path in zips:
        try:
            df = _parse_zip(zip_path.read_bytes())
            rows = to_storage_rows(df, symbol=args.symbol, interval=args.interval)
            n = storage.upsert_candles(rows)
            total_inserted += n
            logger.info("Loaded %s: %d rows (%d new)", zip_path.name, len(df), n)
        except Exception as exc:
            logger.error("Failed to process %s: %s", zip_path.name, exc)

    logger.info("Backfill complete. Total new rows inserted: %d", total_inserted)


if __name__ == "__main__":
    main()
