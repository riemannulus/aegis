"""Page 4: PnL analytics and attribution dashboard."""

from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from backoffice import api_client as api
from backoffice.components.charts import equity_curve_chart, drawdown_chart, bar_chart

st.set_page_config(page_title="PnL Analytics — Aegis", layout="wide")
st.title("PnL Analytics & Attribution")

# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------
trades_raw = api.get_trades(1000) or []
equity_data = api.get_equity_curve() or []
perf = api.get_performance_summary() or {}
attribution = api.get_attribution() or {}

if not trades_raw:
    st.info("No trades recorded yet.")
    st.stop()

df = pd.DataFrame(trades_raw)
for col in ["entry_time", "exit_time", "timestamp"]:
    if col in df.columns:
        df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)
if "pnl" not in df.columns and "net_pnl" in df.columns:
    df["pnl"] = df["net_pnl"]
time_col = "exit_time" if "exit_time" in df.columns else "timestamp"

# ---------------------------------------------------------------------------
# Key metrics
# ---------------------------------------------------------------------------
st.subheader("Performance Metrics")
c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Sharpe", f"{perf.get('sharpe_ratio', 0):.2f}")
c2.metric("Sortino", f"{perf.get('sortino_ratio', 0):.2f}")
c3.metric("Calmar", f"{perf.get('calmar_ratio', 0):.2f}")
c4.metric("Win Rate", f"{perf.get('win_rate', 0):.1%}")
c5.metric("Profit Factor", f"{perf.get('profit_factor', 0):.2f}")
c6.metric("Exp. Value", f"${perf.get('expected_value', 0):.2f}")

st.divider()

# ---------------------------------------------------------------------------
# Equity curve + drawdown
# ---------------------------------------------------------------------------
col_l, col_r = st.columns(2)
with col_l:
    if equity_data:
        eq_df = pd.DataFrame(equity_data)
        if "timestamp" not in eq_df.columns and "exit_time" in eq_df.columns:
            eq_df = eq_df.rename(columns={"exit_time": "timestamp"})
        eq_df["timestamp"] = pd.to_datetime(eq_df["timestamp"])
        st.plotly_chart(equity_curve_chart(eq_df, title="Equity Curve vs BTC Buy&Hold"), use_container_width=True)
    else:
        st.info("No equity curve data.")

with col_r:
    if equity_data:
        st.plotly_chart(drawdown_chart(eq_df, title="Drawdown (Underwater Chart)"), use_container_width=True)

# ---------------------------------------------------------------------------
# PnL heatmaps
# ---------------------------------------------------------------------------
st.subheader("PnL Heatmaps")
if time_col in df.columns:
    df_sorted = df.sort_values(time_col)
    df_sorted["hour"] = df_sorted[time_col].dt.hour
    df_sorted["weekday"] = df_sorted[time_col].dt.day_name()
    df_sorted["date"] = df_sorted[time_col].dt.date

    ht1, ht2 = st.columns(2)
    with ht1:
        hourly = df_sorted.groupby("hour")["pnl"].mean().reset_index()
        fig = px.bar(hourly, x="hour", y="pnl", title="Avg PnL by Hour (UTC)",
                     color="pnl", color_continuous_scale="RdYlGn", color_continuous_midpoint=0,
                     template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)

    with ht2:
        daily = df_sorted.groupby("weekday")["pnl"].mean().reset_index()
        day_order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
        daily["weekday"] = pd.Categorical(daily["weekday"], categories=day_order, ordered=True)
        daily = daily.sort_values("weekday")
        fig2 = px.bar(daily, x="weekday", y="pnl", title="Avg PnL by Day of Week",
                      color="pnl", color_continuous_scale="RdYlGn", color_continuous_midpoint=0,
                      template="plotly_dark")
        st.plotly_chart(fig2, use_container_width=True)
else:
    st.info("No timestamp data available for heatmaps.")

# ---------------------------------------------------------------------------
# PnL distribution histogram
# ---------------------------------------------------------------------------
st.subheader("PnL Distribution")
if "pnl" in df.columns and not df.empty:
    fig_hist = px.histogram(df, x="pnl", nbins=50, title="PnL Distribution",
                            template="plotly_dark",
                            color_discrete_sequence=["#00d4aa"])
    fig_hist.add_vline(x=0, line_dash="dash", line_color="red")
    st.plotly_chart(fig_hist, use_container_width=True)
else:
    st.info("No trade data for PnL distribution.")

# ---------------------------------------------------------------------------
# Attribution tabs
# ---------------------------------------------------------------------------
st.subheader("PnL Attribution")
atab1, atab2, atab3, atab4, atab5 = st.tabs([
    "Model Contribution", "Regime Performance", "Long vs Short",
    "Time of Day", "Funding & Slippage"
])

with atab1:
    model_df = attribution.get("model_contribution")
    if isinstance(model_df, list):
        model_df = pd.DataFrame(model_df)
    if model_df is not None and not (isinstance(model_df, pd.DataFrame) and model_df.empty):
        st.plotly_chart(
            bar_chart(pd.DataFrame(model_df), x="model", y="total_attributed_pnl",
                      title="Model Contribution to PnL"),
            use_container_width=True,
        )
    else:
        st.info("No attribution data yet.")

with atab2:
    regime_df = attribution.get("regime_performance")
    if isinstance(regime_df, list):
        regime_df = pd.DataFrame(regime_df)
    if regime_df is not None and not (isinstance(regime_df, pd.DataFrame) and regime_df.empty):
        st.plotly_chart(
            bar_chart(pd.DataFrame(regime_df), x="regime", y="total_net_pnl", title="PnL by Regime"),
            use_container_width=True,
        )
        st.dataframe(pd.DataFrame(regime_df), use_container_width=True, hide_index=True)
    else:
        if "regime" in df.columns:
            rdf = df.groupby("regime")["pnl"].agg(["sum","mean","count"]).reset_index()
            st.dataframe(rdf, use_container_width=True)
        else:
            st.info("No regime data.")

with atab3:
    dir_df = attribution.get("direction_performance")
    if isinstance(dir_df, list):
        dir_df = pd.DataFrame(dir_df)
    if dir_df is not None and not (isinstance(dir_df, pd.DataFrame) and dir_df.empty):
        st.plotly_chart(
            bar_chart(pd.DataFrame(dir_df), x="direction_label", y="total_net_pnl",
                      title="Long vs Short PnL"),
            use_container_width=True,
        )
    else:
        if "side" in df.columns:
            sdf = df.groupby("side")["pnl"].agg(["sum","mean","count"]).reset_index()
            st.dataframe(sdf, use_container_width=True)
        else:
            st.info("No direction data.")

with atab4:
    tod_df = attribution.get("time_of_day_performance")
    if isinstance(tod_df, list):
        tod_df = pd.DataFrame(tod_df)
    if tod_df is not None and not (isinstance(tod_df, pd.DataFrame) and tod_df.empty):
        fig = px.bar(pd.DataFrame(tod_df), x="hour", y="avg_net_pnl",
                     color="avg_net_pnl", color_continuous_scale="RdYlGn",
                     color_continuous_midpoint=0, title="Avg PnL by Hour",
                     template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No time-of-day data.")

with atab5:
    cost_info = attribution.get("funding_cost_share", {})
    slip_info = attribution.get("slippage_impact", {})
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Funding Costs")
        if cost_info:
            st.metric("Total Gross PnL", f"${cost_info.get('total_gross_pnl', 0):.2f}")
            st.metric("Total Funding Cost", f"${cost_info.get('total_funding_cost', 0):.2f}")
            share = cost_info.get("funding_share_pct", 0)
            st.metric("Funding Share of Gross PnL", f"{share:.1f}%")
        elif "funding_cost" in df.columns:
            st.metric("Total Funding Cost", f"${df['funding_cost'].sum():.2f}")
    with c2:
        st.subheader("Slippage Impact")
        if slip_info:
            st.metric("Total Slippage (USDT)", f"${slip_info.get('total_slippage_usdt', 0):.2f}")
            st.metric("Avg Slippage (bps)", f"{slip_info.get('avg_slippage_bps', 0):.1f}")
