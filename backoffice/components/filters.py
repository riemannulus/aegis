"""Shared filter components for the Aegis backoffice dashboard."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import streamlit as st


def date_range_filter(
    key_prefix: str = "date",
    default_days: int = 30,
) -> tuple[date, date]:
    """Render start/end date pickers and return (start_date, end_date)."""
    col1, col2 = st.columns(2)
    with col1:
        start = st.date_input(
            "Start date",
            value=date.today() - timedelta(days=default_days),
            key=f"{key_prefix}_start",
        )
    with col2:
        end = st.date_input(
            "End date",
            value=date.today(),
            key=f"{key_prefix}_end",
        )
    return start, end


def decision_type_filter(key: str = "decision_type") -> list[str]:
    """Multi-select filter for decision types."""
    options = ["EXECUTE", "SKIP", "REJECTED_BY_RISK", "REDUCE", "CLOSE"]
    return st.multiselect(
        "Decision type",
        options=options,
        default=options,
        key=key,
    )


def direction_filter(key: str = "direction") -> list[str]:
    """Multi-select filter for trade direction."""
    options = ["LONG", "SHORT", "FLAT"]
    return st.multiselect(
        "Direction",
        options=options,
        default=options,
        key=key,
    )


def regime_filter(key: str = "regime") -> list[str]:
    """Multi-select filter for market regime."""
    options = ["TRENDING", "RANGING", "VOLATILE"]
    return st.multiselect(
        "Regime",
        options=options,
        default=options,
        key=key,
    )


def result_filter(key: str = "result") -> list[str]:
    """Multi-select filter for win/loss."""
    options = ["WIN", "LOSS"]
    return st.multiselect(
        "Result",
        options=options,
        default=options,
        key=key,
    )


def log_level_filter(key: str = "log_level") -> list[str]:
    """Multi-select filter for log levels."""
    options = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    return st.multiselect(
        "Log level",
        options=options,
        default=["INFO", "WARNING", "ERROR", "CRITICAL"],
        key=key,
    )
