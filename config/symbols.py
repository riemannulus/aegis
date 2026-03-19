"""Trading symbol configuration."""

# Primary trading symbol (CCXT Futures notation)
PRIMARY_SYMBOL = "BTC/USDT:USDT"

# Binance Vision symbol notation (no slash, futures um = USDS-M)
BINANCE_VISION_SYMBOL = "BTCUSDT"

# Supported symbols for future expansion
SUPPORTED_SYMBOLS = [
    "BTC/USDT:USDT",
]

# Map CCXT symbol → Binance Vision symbol
CCXT_TO_VISION: dict[str, str] = {
    "BTC/USDT:USDT": "BTCUSDT",
}

# Map Binance Vision symbol → CCXT symbol
VISION_TO_CCXT: dict[str, str] = {v: k for k, v in CCXT_TO_VISION.items()}
