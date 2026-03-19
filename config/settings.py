from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Binance API Keys
    CT_BINANCE_API_KEY: str = ""
    CT_BINANCE_API_SECRET: str = ""
    CT_BINANCE_TESTNET_API_KEY: str = ""
    CT_BINANCE_TESTNET_API_SECRET: str = ""

    # Trading
    TRADING_SYMBOL: str = "BTC/USDT:USDT"
    TIMEFRAME: str = "30m"

    # Futures settings
    MARKET_TYPE: str = "future"          # CCXT defaultType — do NOT change to 'spot'
    LEVERAGE: int = 3                     # Default 3x, max 10x
    MARGIN_TYPE: str = "isolated"         # isolated only — cross margin exposes full account
    POSITION_MODE: str = "one-way"        # simpler than hedge mode

    # Risk parameters
    MAX_POSITION_RATIO: float = 0.3       # max 30% of capital
    MAX_DAILY_LOSS_RATIO: float = 0.05    # max 5% daily loss
    MAX_DRAWDOWN_RATIO: float = 0.10      # max 10% drawdown
    RISK_REWARD_RATIO: float = 2.0
    MIN_SIGNAL_THRESHOLD: float = 1.0     # minimum Z-score to trade

    # Environment
    USE_TESTNET: bool = True              # ALWAYS True during dev/test
    BINANCE_VISION_BASE_URL: str = "https://data.binance.vision"

    # Telegram
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    # Derived properties (set by validator)
    api_key: str = ""
    api_secret: str = ""
    log_tag: str = ""
    telegram_tag: str = ""

    @model_validator(mode="after")
    def branch_by_network(self) -> "Settings":
        if self.USE_TESTNET:
            self.api_key = self.CT_BINANCE_TESTNET_API_KEY
            self.api_secret = self.CT_BINANCE_TESTNET_API_SECRET
            self.log_tag = "[TESTNET]"
            self.telegram_tag = "[TESTNET]"
        else:
            self.api_key = self.CT_BINANCE_API_KEY
            self.api_secret = self.CT_BINANCE_API_SECRET
            self.log_tag = "[MAINNET]"
            self.telegram_tag = "[MAINNET]"
        return self

    @property
    def sandbox_mode(self) -> bool:
        return self.USE_TESTNET

    @property
    def requires_safety_confirmation(self) -> bool:
        """Extra safety check before order execution on mainnet."""
        return not self.USE_TESTNET

    def build_ccxt_exchange(self):
        """Build a configured CCXT Binance Futures exchange instance."""
        import ccxt
        exchange = ccxt.binance({
            "apiKey": self.api_key,
            "secret": self.api_secret,
            "enableRateLimit": True,
            "options": {
                "defaultType": self.MARKET_TYPE,   # must be 'future'
                "adjustForTimeDifference": True,
            },
        })
        if self.USE_TESTNET:
            exchange.set_sandbox_mode(True)
        return exchange


settings = Settings()
