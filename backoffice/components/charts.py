"""Shared Plotly chart components for the Aegis backoffice dashboard."""

from __future__ import annotations

from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots


def equity_curve_chart(
    equity_df: pd.DataFrame,
    btc_df: Optional[pd.DataFrame] = None,
    title: str = "Equity Curve",
) -> go.Figure:
    """Line chart of equity curve, optionally overlaid with BTC Buy&Hold."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=equity_df["timestamp"] if "timestamp" in equity_df.columns else equity_df.index,
        y=equity_df["equity"],
        mode="lines",
        name="Aegis Strategy",
        line=dict(color="#00d4aa", width=2),
    ))
    if btc_df is not None and "btc_equity" in btc_df.columns:
        fig.add_trace(go.Scatter(
            x=btc_df["timestamp"],
            y=btc_df["btc_equity"],
            mode="lines",
            name="BTC Buy & Hold",
            line=dict(color="#f7931a", width=1.5, dash="dash"),
        ))
    fig.update_layout(
        title=title,
        xaxis_title="Time",
        yaxis_title="Equity (USDT)",
        template="plotly_dark",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=20, t=60, b=40),
    )
    return fig


def drawdown_chart(equity_df: pd.DataFrame, title: str = "Drawdown") -> go.Figure:
    """Underwater / drawdown chart."""
    eq = equity_df["equity"]
    hwm = eq.cummax()
    drawdown = (eq - hwm) / hwm * 100

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=equity_df["timestamp"] if "timestamp" in equity_df.columns else equity_df.index,
        y=drawdown,
        fill="tozeroy",
        mode="lines",
        name="Drawdown %",
        line=dict(color="#ff4444"),
        fillcolor="rgba(255,68,68,0.3)",
    ))
    fig.update_layout(
        title=title,
        xaxis_title="Time",
        yaxis_title="Drawdown (%)",
        template="plotly_dark",
        margin=dict(l=40, r=20, t=60, b=40),
    )
    return fig


def candlestick_chart(
    candles_df: pd.DataFrame,
    entry_time: Optional[pd.Timestamp] = None,
    exit_time: Optional[pd.Timestamp] = None,
    entry_price: Optional[float] = None,
    exit_price: Optional[float] = None,
    title: str = "Price Chart",
) -> go.Figure:
    """OHLC candlestick chart with optional entry/exit markers."""
    fig = go.Figure(data=[go.Candlestick(
        x=candles_df["timestamp"],
        open=candles_df["open"],
        high=candles_df["high"],
        low=candles_df["low"],
        close=candles_df["close"],
        name="BTC/USDT",
    )])
    if entry_time is not None and entry_price is not None:
        fig.add_trace(go.Scatter(
            x=[entry_time], y=[entry_price],
            mode="markers",
            marker=dict(symbol="triangle-up", size=14, color="#00ff88"),
            name="Entry",
        ))
    if exit_time is not None and exit_price is not None:
        fig.add_trace(go.Scatter(
            x=[exit_time], y=[exit_price],
            mode="markers",
            marker=dict(symbol="triangle-down", size=14, color="#ff4444"),
            name="Exit",
        ))
    fig.update_layout(
        title=title,
        xaxis_title="Time",
        yaxis_title="Price (USDT)",
        template="plotly_dark",
        xaxis_rangeslider_visible=False,
        margin=dict(l=40, r=20, t=60, b=40),
    )
    return fig


def bar_chart(
    df: pd.DataFrame,
    x: str,
    y: str,
    color: Optional[str] = None,
    title: str = "",
    xaxis_title: str = "",
    yaxis_title: str = "",
) -> go.Figure:
    """Generic bar chart."""
    fig = px.bar(
        df, x=x, y=y,
        color=color,
        title=title,
        template="plotly_dark",
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig.update_layout(
        xaxis_title=xaxis_title or x,
        yaxis_title=yaxis_title or y,
        margin=dict(l=40, r=20, t=60, b=40),
    )
    return fig


def heatmap_chart(
    data: pd.DataFrame,
    x: str,
    y: str,
    z: str,
    title: str = "Heatmap",
) -> go.Figure:
    """Generic heatmap for hourly/day-of-week PnL."""
    pivot = data.pivot_table(values=z, index=y, columns=x, aggfunc="mean")
    fig = go.Figure(data=go.Heatmap(
        z=pivot.values,
        x=[str(c) for c in pivot.columns],
        y=[str(r) for r in pivot.index],
        colorscale="RdYlGn",
        zmid=0,
    ))
    fig.update_layout(
        title=title,
        template="plotly_dark",
        margin=dict(l=40, r=20, t=60, b=40),
    )
    return fig


def pie_chart(labels: list, values: list, title: str = "") -> go.Figure:
    """Pie chart for router weights or model contributions."""
    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        hole=0.35,
    )])
    fig.update_layout(
        title=title,
        template="plotly_dark",
        margin=dict(l=20, r=20, t=60, b=20),
    )
    return fig


def waterfall_latency_chart(stages: list[str], durations_ms: list[float]) -> go.Figure:
    """Waterfall chart showing pipeline stage latencies."""
    fig = go.Figure(go.Waterfall(
        orientation="v",
        measure=["relative"] * len(stages),
        x=stages,
        y=durations_ms,
        connector=dict(line=dict(color="rgb(63, 63, 63)")),
        increasing=dict(marker=dict(color="#00d4aa")),
        decreasing=dict(marker=dict(color="#ff4444")),
    ))
    fig.update_layout(
        title="Pipeline Latency Breakdown",
        xaxis_title="Stage",
        yaxis_title="Duration (ms)",
        template="plotly_dark",
        margin=dict(l=40, r=20, t=60, b=60),
    )
    return fig


def gauge_chart(value: float, min_val: float, max_val: float, title: str, threshold_pct: float = 0.8) -> go.Figure:
    """Gauge chart for drawdown / liquidation distance."""
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=value,
        domain={"x": [0, 1], "y": [0, 1]},
        title={"text": title},
        gauge={
            "axis": {"range": [min_val, max_val]},
            "bar": {"color": "#00d4aa"},
            "steps": [
                {"range": [min_val, max_val * 0.5], "color": "#1a3a2a"},
                {"range": [max_val * 0.5, max_val * 0.8], "color": "#3a3a1a"},
                {"range": [max_val * 0.8, max_val], "color": "#3a1a1a"},
            ],
            "threshold": {
                "line": {"color": "red", "width": 4},
                "thickness": 0.75,
                "value": max_val * threshold_pct,
            },
        },
    ))
    fig.update_layout(template="plotly_dark", margin=dict(l=20, r=20, t=60, b=20))
    return fig


def ic_trend_chart(ic_df: pd.DataFrame, title: str = "IC Trend") -> go.Figure:
    """Line chart of IC values over time for each model."""
    fig = go.Figure()
    colors = {"lgbm": "#00d4aa", "tra": "#f7931a", "adarnn": "#a855f7", "ensemble": "#3b82f6"}
    for col in [c for c in ic_df.columns if c != "date"]:
        fig.add_trace(go.Scatter(
            x=ic_df["date"],
            y=ic_df[col],
            mode="lines",
            name=col.upper(),
            line=dict(color=colors.get(col, "#ffffff")),
        ))
    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    fig.update_layout(
        title=title,
        xaxis_title="Date",
        yaxis_title="IC",
        template="plotly_dark",
        margin=dict(l=40, r=20, t=60, b=40),
    )
    return fig
