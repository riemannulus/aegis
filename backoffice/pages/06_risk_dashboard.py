"""Page 6: Risk status dashboard."""

from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from backoffice import api_client as api
from backoffice.components.charts import gauge_chart, drawdown_chart

st.set_page_config(page_title="Risk Dashboard — Aegis", layout="wide")
st.title("Risk Dashboard")

# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------
risk_status = api.get_risk_status() or {}
metrics = api.get_metrics() or {}
equity_data = api.get_equity_curve() or []
risk_events = api.get_risk_events(100) or []

# ---------------------------------------------------------------------------
# Key risk metrics
# ---------------------------------------------------------------------------
st.subheader("Current Risk Status")

drawdown_pct = risk_status.get("current_drawdown_pct", metrics.get("max_drawdown", 0)) * 100
daily_loss_used = risk_status.get("daily_loss_used_pct", 0) * 100
consecutive_losses = risk_status.get("consecutive_losses", 0)
risk_level = risk_status.get("risk_level", "unknown")
position_ratio = risk_status.get("position_ratio", 0)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Current Drawdown", f"{drawdown_pct:.2f}%",
          delta_color="inverse")
c2.metric("Daily Loss Used", f"{daily_loss_used:.2f}% / 5%",
          delta_color="inverse")
c3.metric("Consecutive Losses", f"{consecutive_losses} / 5",
          delta_color="inverse")
c4.metric("Risk Level", risk_level.upper())

st.divider()

# ---------------------------------------------------------------------------
# Drawdown gauge
# ---------------------------------------------------------------------------
st.subheader("Drawdown Gauge")
col_g, col_info = st.columns([1, 2])
with col_g:
    fig_gauge = gauge_chart(
        value=min(drawdown_pct, 10),
        min_val=0,
        max_val=10,
        title="Drawdown (%)",
        threshold_pct=0.8,
    )
    st.plotly_chart(fig_gauge, use_container_width=True)

with col_info:
    st.markdown("""
    **Drawdown Action Levels:**
    | Level | Threshold | Action |
    |-------|-----------|--------|
    | ⚠️ Warning | 5% | Telegram alert |
    | 🔶 Reduce | 8% | No new positions + 50% reduction |
    | 🔴 Halt | 10% | Full liquidation + system pause |
    """)
    if drawdown_pct >= 10:
        st.error("🔴 DRAWDOWN HALT LEVEL REACHED — System paused.")
    elif drawdown_pct >= 8:
        st.warning("🔶 Drawdown Reduce level — no new positions.")
    elif drawdown_pct >= 5:
        st.warning("⚠️ Drawdown Warning level.")
    else:
        st.success("✅ Drawdown within normal range.")

st.divider()

# ---------------------------------------------------------------------------
# Equity + HWM overlay
# ---------------------------------------------------------------------------
if equity_data:
    eq_df = pd.DataFrame(equity_data)
    if "timestamp" not in eq_df.columns and "exit_time" in eq_df.columns:
        eq_df = eq_df.rename(columns={"exit_time": "timestamp"})
    if "equity" not in eq_df.columns and "cum_pnl" in eq_df.columns:
        eq_df["equity"] = 10000 + eq_df["cum_pnl"]
    if "timestamp" not in eq_df.columns or "equity" not in eq_df.columns:
        st.info("Equity curve data missing required columns.")
    else:
        eq_df["timestamp"] = pd.to_datetime(eq_df["timestamp"])
        eq_df["hwm"] = eq_df["equity"].cummax()

        fig_eq = go.Figure()
        fig_eq.add_trace(go.Scatter(x=eq_df["timestamp"], y=eq_df["equity"],
                                    mode="lines", name="Equity", line=dict(color="#00d4aa")))
        fig_eq.add_trace(go.Scatter(x=eq_df["timestamp"], y=eq_df["hwm"],
                                    mode="lines", name="High Water Mark",
                                    line=dict(color="#f7931a", dash="dot")))
        fig_eq.update_layout(title="Account Equity vs High Water Mark",
                             template="plotly_dark", xaxis_title="Time", yaxis_title="USDT",
                             margin=dict(l=40, r=20, t=60, b=40))
        st.plotly_chart(fig_eq, use_container_width=True)

        st.plotly_chart(drawdown_chart(eq_df, title="Drawdown History"), use_container_width=True)

# ---------------------------------------------------------------------------
# Daily loss budget bar
# ---------------------------------------------------------------------------
st.subheader("Daily Loss Budget")
col_d, _ = st.columns([1, 2])
with col_d:
    budget_pct = min(daily_loss_used / 5.0, 1.0)
    color = "red" if budget_pct > 0.8 else ("orange" if budget_pct > 0.5 else "green")
    st.markdown(f"**Used: {daily_loss_used:.1f}% of 5% daily limit**")
    st.progress(budget_pct)

# ---------------------------------------------------------------------------
# Risk event timeline
# ---------------------------------------------------------------------------
st.subheader("Risk Event Timeline")
if risk_events:
    ev_df = pd.DataFrame(risk_events)
    if "timestamp" in ev_df.columns:
        ev_df["timestamp"] = pd.to_datetime(ev_df["timestamp"], errors="coerce")
        ev_df = ev_df.sort_values("timestamp", ascending=False)
    st.dataframe(ev_df, use_container_width=True, hide_index=True)
else:
    st.info("No risk events recorded.")

# ---------------------------------------------------------------------------
# Liquidation proximity history
# ---------------------------------------------------------------------------
st.subheader("Liquidation Proximity History")
liq_history = risk_status.get("liquidation_proximity_history", [])
if liq_history:
    liq_df = pd.DataFrame(liq_history)
    liq_df = liq_df.sort_values("distance_pct", ascending=True).head(10)
    st.dataframe(liq_df, use_container_width=True, hide_index=True)
else:
    st.info("No liquidation proximity data.")
