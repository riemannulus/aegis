"""Abstract base class for Aegis order execution backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseExecutor(ABC):
    """Shared interface for BinanceExecutor and PaperTrader."""

    # ------------------------------------------------------------------
    # Account / Position queries
    # ------------------------------------------------------------------

    @abstractmethod
    def get_balance(self) -> dict[str, Any]:
        """Return current account balance information."""
        ...

    @abstractmethod
    def get_position(self, symbol: str) -> dict[str, Any]:
        """Return current open position for the given symbol."""
        ...

    # ------------------------------------------------------------------
    # Order operations
    # ------------------------------------------------------------------

    @abstractmethod
    def create_market_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        params: dict | None = None,
    ) -> dict[str, Any]:
        """Submit a market order. side: 'buy' or 'sell'."""
        ...

    @abstractmethod
    def create_limit_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float,
        params: dict | None = None,
    ) -> dict[str, Any]:
        """Submit a limit order."""
        ...

    @abstractmethod
    def close_position(self, symbol: str, params: dict | None = None) -> dict[str, Any]:
        """Close the entire open position for symbol at market price."""
        ...

    @abstractmethod
    def cancel_order(self, order_id: str, symbol: str) -> dict[str, Any]:
        """Cancel a pending order by ID."""
        ...

    @abstractmethod
    def get_order_status(self, order_id: str, symbol: str) -> dict[str, Any]:
        """Return the current status of an order."""
        ...

    # ------------------------------------------------------------------
    # Futures-specific setup
    # ------------------------------------------------------------------

    @abstractmethod
    def is_testnet(self) -> bool:
        """Return True if this executor is connected to testnet."""
        ...

    @abstractmethod
    def initialize_futures(self, symbol: str, leverage: int, margin_type: str) -> None:
        """Set leverage and margin type for a futures symbol.

        Should be called once at startup.
        leverage: integer (e.g. 3)
        margin_type: 'isolated' or 'cross' (only 'isolated' is supported)
        """
        ...
