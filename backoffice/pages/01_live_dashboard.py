"""Page 1: Real-time operations dashboard."""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from backoffice import api_client as api
from backoffice.components.charts import equity_curve_chart

st.set_page_config(page_title="Live Dashboard — Aegis", layout="wide")
st.title("Live Dashboard")

# Auto-refresh every 30 seconds
if st.button("Refresh"):
    st.rerun()

# ---------------------------------------------------------------------------
# Fetch data
# ---------------------------------------------------------------------------
health = api.get_health() or {}
position = api.get_positions() or {}
metrics = api.get_metrics() or {}
signals = api.get_latest_signals(5) or []
decisions = api.get_decisions(5) or []
equity_data = api.get_equity_curve() or []

# ---------------------------------------------------------------------------
# System status bar
# ---------------------------------------------------------------------------
system_status = health.get("status", "unknown")
env = health.get("environment", "TESTNET")
use_testnet = env != "MAINNET"

status_emoji = {"running": "🟢", "warning": "🟡", "stopped": "🔴"}.get(system_status.lower(), "⚪")
env_badge = "🟡 TESTNET" if use_testnet else "🔴 MAINNET"

col1, col2, col3 = st.columns([2, 1, 1])
with col1:
    st.subheader(f"{status_emoji} System: {system_status.upper()}  |  {env_badge}")
with col2:
    last_signal = health.get("last_signal_at", "N/A")
    st.metric("Last Signal", last_signal)
with col3:
    model_status = health.get("models_loaded", False)
    st.metric("Models", "Loaded ✓" if model_status else "Not loaded ✗")

st.divider()

# ---------------------------------------------------------------------------
# Position card
# ---------------------------------------------------------------------------
st.subheader("Current Futures Position")

if position:
    side = position.get("side", "FLAT")
    size = position.get("size", 0.0)
    leverage = position.get("leverage", 3)
    entry_price = position.get("entry_price", 0.0)
    mark_price = position.get("mark_price", 0.0)
    liq_price = position.get("liquidation_price", 0.0)
    unrealized_pnl = position.get("unrealized_pnl", 0.0)

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Side", side, delta=None)
    c2.metric("Size (BTC)", f"{size:.4f}")
    c3.metric("Leverage", f"{leverage}x")
    c4.metric("Entry Price", f"${entry_price:,.2f}")
    c5.metric("Mark Price", f"${mark_price:,.2f}")
    c6.metric("Unrealized PnL", f"${unrealized_pnl:+.2f}")

    # Liquidation distance gauge
    if liq_price > 0 and mark_price > 0:
        if side == "LONG":
            liq_dist_pct = (mark_price - liq_price) / mark_price * 100
        else:
            liq_dist_pct = (liq_price - mark_price) / mark_price * 100

        pct_capped = max(0, min(100, liq_dist_pct))
        color = "red" if pct_capped < 20 else ("orange" if pct_capped < 50 else "green")
        st.markdown(f"**Liquidation Distance:** {liq_dist_pct:.1f}% away from `${liq_price:,.2f}`")
        st.progress(pct_capped / 100, text=f"{pct_capped:.1f}% safe margin")
else:
    st.info("No open position.")

st.divider()

# ---------------------------------------------------------------------------
# Today's PnL summary
# ---------------------------------------------------------------------------
st.subheader("Today's PnL Summary")

realized = metrics.get("today_realized_pnl", 0.0)
funding = metrics.get("today_funding_cost", 0.0)
unrealized = metrics.get("unrealized_pnl", 0.0)
net_today = realized - abs(funding) + unrealized

c1, c2, c3, c4 = st.columns(4)
c1.metric("Realized PnL", f"${realized:+.2f}")
c2.metric("Unrealized PnL", f"${unrealized:+.2f}")
c3.metric("Funding Cost", f"${funding:+.2f}")
c4.metric("Net PnL", f"${net_today:+.2f}", delta=f"{net_today/100:.2%}" if net_today else None)

st.divider()

# ---------------------------------------------------------------------------
# Equity curve
# ---------------------------------------------------------------------------
st.subheader("Equity Curve")
if equity_data:
    eq_df = pd.DataFrame(equity_data)
    if "timestamp" not in eq_df.columns and "exit_time" in eq_df.columns:
        eq_df = eq_df.rename(columns={"exit_time": "timestamp"})
    eq_df["timestamp"] = pd.to_datetime(eq_df["timestamp"])
    st.plotly_chart(equity_curve_chart(eq_df), use_container_width=True)
else:
    st.info("No equity data available yet.")

st.divider()

# ---------------------------------------------------------------------------
# Funding rate countdown
# ---------------------------------------------------------------------------
st.subheader("Funding Rate")
funding_info = api.get_funding_history(1) or []
if funding_info:
    last_fr = funding_info[-1]
    fr_val = last_fr.get("funding_rate", 0.0)
    fr_color = "red" if abs(fr_val) > 0.001 else "green"
    st.markdown(f"**Current Funding Rate:** <span style='color:{fr_color}'>{fr_val*100:.4f}%</span>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Recent trades & decisions
# ---------------------------------------------------------------------------
col_l, col_r = st.columns(2)

with col_l:
    st.subheader("Recent Signals (last 5)")
    if signals:
        sig_df = pd.DataFrame(signals)
        st.dataframe(sig_df, use_container_width=True, hide_index=True)
    else:
        st.info("No signals yet.")

with col_r:
    st.subheader("Recent Decisions (last 5)")
    if decisions:
        dec_df = pd.DataFrame([
            {
                "time": d.get("timestamp", ""),
                "decision": d.get("decision", ""),
                "direction": d.get("direction", ""),
                "z_score": f'{d.get("z_score", 0):.2f}',
                "regime": d.get("regime", ""),
                "reason": (d.get("reason") or "")[:60],
            }
            for d in decisions
        ])
        st.dataframe(dec_df, use_container_width=True, hide_index=True)
    else:
        st.info("No decisions yet.")

st.divider()

# ---------------------------------------------------------------------------
# Emergency exit
# ---------------------------------------------------------------------------
st.subheader("Emergency Controls")
with st.expander("Danger Zone", expanded=False):
    st.warning("Emergency exit will close ALL open futures positions immediately at market price.")
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("EMERGENCY EXIT ALL POSITIONS", type="primary"):
            st.session_state["confirm_exit"] = True
    with col_b:
        if st.session_state.get("confirm_exit"):
            if st.button("Confirm — YES, close all positions", type="primary"):
                result = api.post_emergency_exit()
                if result:
                    st.success("Emergency exit executed.")
                else:
                    st.error("API unavailable — could not execute emergency exit.")
                st.session_state["confirm_exit"] = False
            if st.button("Cancel"):
                st.session_state["confirm_exit"] = False
