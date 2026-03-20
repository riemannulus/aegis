"""Fetch BTC/USDT 30m futures candles from Binance via CCXT and insert into SQLite."""
import sys
import time

sys.path.insert(0, "/Users/suho/Workspaces/aegis")

import ccxt
from data.storage import Storage

exchange = ccxt.binance({"options": {"defaultType": "future"}})
storage = Storage()

symbol = "BTC/USDT:USDT"
timeframe = "30m"
since = int(ccxt.Exchange.parse8601("2024-07-01T00:00:00Z"))
end = int(ccxt.Exchange.parse8601("2025-03-01T00:00:00Z"))

all_candles = []

print(f"Fetching {symbol} {timeframe} candles from 2024-07-01 to 2025-03-01...")

while since < end:
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
    if not ohlcv:
        break
    batch = []
    for c in ohlcv:
        ts = c[0]
        if ts >= end:
            break
        batch.append({
            "timestamp": ts,
            "symbol": "BTCUSDT",
            "interval": "30m",
            "open": c[1],
            "high": c[2],
            "low": c[3],
            "close": c[4],
            "volume": c[5],
        })
    if not batch:
        break
    all_candles.extend(batch)
    since = ohlcv[-1][0] + 1
    time.sleep(0.1)
    if len(all_candles) % 5000 < len(batch):
        print(f"  Fetched {len(all_candles)} candles so far...")

print(f"Total fetched: {len(all_candles)} candles. Inserting into DB...")

inserted = 0
for i in range(0, len(all_candles), 500):
    batch = all_candles[i : i + 500]
    inserted += storage.upsert_candles(batch)

print(f"Done. Inserted {inserted} new rows (total fetched: {len(all_candles)}).")
