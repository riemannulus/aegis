"""Page 8: System operations — logs, latency, manual controls."""

from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from pathlib import Path

import pandas as pd
import streamlit as st

from backoffice import api_client as api
from backoffice.components.filters import log_level_filter
from backoffice.components.charts import waterfall_latency_chart

st.set_page_config(page_title="System Ops — Aegis", layout="wide")
st.title("System Operations")
st.caption("Logs, latency monitoring, and manual controls.")

# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------
health = api.get_health() or {}
scheduler = api.get_scheduler_status() or {}
latency = api.get_pipeline_latency() or {}

# ---------------------------------------------------------------------------
# System status overview
# ---------------------------------------------------------------------------
st.subheader("System Health")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Status", health.get("status", "unknown").upper())
c2.metric("Environment", health.get("environment", "TESTNET"))
c3.metric("Uptime", health.get("uptime", "N/A"))
c4.metric("API Version", health.get("version", "N/A"))

# Configuration from settings (direct import as fallback)
st.subheader("System Configuration")
try:
    from config.settings import settings as _settings
    cc1, cc2, cc3, cc4, cc5, cc6 = st.columns(6)
    cc1.metric("Network", "TESTNET" if _settings.USE_TESTNET else "MAINNET")
    cc2.metric("Symbol", _settings.TRADING_SYMBOL)
    cc3.metric("Timeframe", _settings.TIMEFRAME)
    cc4.metric("Leverage", f"{_settings.LEVERAGE}x")
    cc5.metric("Margin Type", _settings.MARGIN_TYPE)
    cc6.metric("Max DD", f"{_settings.MAX_DRAWDOWN_RATIO:.0%}")
    if not _settings.USE_TESTNET:
        st.error("WARNING: USE_TESTNET=False — MAINNET MODE ACTIVE — Real assets at risk!")
    else:
        st.success("USE_TESTNET=True — Testnet mode (safe)")
except Exception:
    st.info("Settings not loaded (run from project root).")

st.divider()

# ---------------------------------------------------------------------------
# Pipeline latency waterfall
# ---------------------------------------------------------------------------
st.subheader("Pipeline Latency Breakdown")
if latency:
    stages = ["Candle Recv", "Feature Calc", "Model Inference", "Signal Convert", "Risk Check", "Order Submit"]
    durations = [
        float(latency.get("candle_recv_ms", 0)),
        float(latency.get("feature_calc_ms", 0)),
        float(latency.get("model_inference_ms", 0)),
        float(latency.get("signal_convert_ms", 0)),
        float(latency.get("risk_check_ms", 0)),
        float(latency.get("order_submit_ms", 0)),
    ]
    total_ms = sum(durations)
    st.plotly_chart(waterfall_latency_chart(stages, durations), use_container_width=True)
    if total_ms > 5000:
        st.warning(f"Total latency {total_ms:.0f}ms exceeds 5s target!")
    else:
        st.success(f"Total latency: {total_ms:.0f}ms (target < 5000ms)")
else:
    st.info("No latency data from API.")

st.divider()

# ---------------------------------------------------------------------------
# WebSocket & data pipeline health
# ---------------------------------------------------------------------------
st.subheader("Data Pipeline Health")
col_a, col_b = st.columns(2)
with col_a:
    ws_status = health.get("websocket_status", "unknown")
    ws_color = "green" if ws_status == "connected" else "red"
    st.markdown(f"**WebSocket:** <span style='color:{ws_color}'>{ws_status}</span>",
                unsafe_allow_html=True)
    st.caption(f"Last heartbeat: {health.get('last_heartbeat', 'N/A')}")
    st.metric("Last Candle", health.get("last_candle_at", "N/A"))
    st.metric("Missing Candles", health.get("missing_candles", 0), delta_color="inverse")

with col_b:
    db_size = health.get("db_size_mb", 0)
    st.metric("DB Size", f"{db_size:.1f} MB")
    api_rate = health.get("api_rate_limit_used_pct", 0)
    st.metric("API Rate Limit Used", f"{api_rate:.0f}%")
    st.progress(min(float(api_rate) / 100.0, 1.0))

# Database stats (direct fallback)
with st.expander("Database Row Counts", expanded=False):
    try:
        from data.storage import Storage, Candle, Trade, Decision, Signal, Order
        storage = Storage()
        with storage._session() as sess:
            db_stats = {
                "Candles": sess.query(Candle).count(),
                "Trades": sess.query(Trade).count(),
                "Decisions": sess.query(Decision).count(),
                "Signals": sess.query(Signal).count(),
                "Orders": sess.query(Order).count(),
            }
        st.dataframe(pd.DataFrame(list(db_stats.items()), columns=["Table", "Rows"]),
                     use_container_width=True, hide_index=True)
    except Exception as e:
        st.caption(f"DB stats unavailable: {e}")

st.divider()

# ---------------------------------------------------------------------------
# Scheduler status
# ---------------------------------------------------------------------------
st.subheader("Scheduler")
if scheduler:
    jobs = scheduler.get("jobs", [])
    if jobs:
        st.dataframe(pd.DataFrame(jobs), use_container_width=True, hide_index=True)
    last_run = scheduler.get("last_run", {})
    if last_run:
        st.json(last_run)
else:
    st.info("Scheduler status unavailable.")

st.divider()

# ---------------------------------------------------------------------------
# Error tracker
# ---------------------------------------------------------------------------
st.subheader("Error Tracker")
errors = api.get_system_logs(level="ERROR", limit=50) or []
if errors:
    err_df = pd.DataFrame(errors)
    st.metric("Recent Errors", len(err_df))
    st.dataframe(err_df, use_container_width=True, hide_index=True)
else:
    st.success("No recent errors.")

st.divider()

# ---------------------------------------------------------------------------
# Log viewer
# ---------------------------------------------------------------------------
st.subheader("Log Viewer")
with st.sidebar:
    st.header("Filters")
    log_levels = log_level_filter()
    log_limit = st.number_input("Max log lines", 50, 500, 200)

all_logs: list = []
for level in log_levels:
    level_logs = api.get_system_logs(level=level, limit=int(log_limit)) or []
    all_logs.extend(level_logs)

if all_logs:
    log_df = pd.DataFrame(all_logs)
    if "timestamp" in log_df.columns:
        log_df["timestamp"] = pd.to_datetime(log_df["timestamp"], errors="coerce")
        log_df = log_df.sort_values("timestamp", ascending=False)
    st.dataframe(log_df, use_container_width=True, hide_index=True)
else:
    st.info("No log entries.")

st.divider()

# ---------------------------------------------------------------------------
# Saved models & raw data files
# ---------------------------------------------------------------------------
col_m, col_d = st.columns(2)
with col_m:
    st.subheader("Saved Models")
    saved_dir = Path("models/saved")
    if saved_dir.exists():
        files = sorted(saved_dir.iterdir())
        if files:
            minfo = [{"name": f.name,
                      "size_kb": f"{f.stat().st_size/1024:.1f}" if f.is_file() else "dir",
                      "modified": pd.Timestamp(f.stat().st_mtime, unit="s").strftime("%Y-%m-%d %H:%M")}
                     for f in files]
            st.dataframe(pd.DataFrame(minfo), use_container_width=True, hide_index=True)
        else:
            st.info("No saved models.")

with col_d:
    st.subheader("Raw Data Files")
    raw_dir = Path("data/raw")
    if raw_dir.exists():
        zips = sorted(raw_dir.glob("*.zip"))
        if zips:
            dinfo = [{"file": f.name, "size_mb": f"{f.stat().st_size/1e6:.1f}"}
                     for f in zips]
            st.dataframe(pd.DataFrame(dinfo), use_container_width=True, hide_index=True)
        else:
            st.info("No raw data files.")

st.divider()

# ---------------------------------------------------------------------------
# Manual controls
# ---------------------------------------------------------------------------
st.subheader("Manual Controls")
st.warning("These controls affect the live trading system. Use with caution.")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("**Trading Control**")
    if st.button("Start Trading", type="primary"):
        result = api.post_control_start()
        st.success("Started." if result else "API unavailable.")

    if st.button("Stop Trading"):
        result = api.post_control_stop()
        st.success("Stopped." if result else "API unavailable.")

with col2:
    st.markdown("**Model Control**")
    if st.button("Force Retrain"):
        if st.session_state.get("_confirm_retrain"):
            result = api.post_force_retrain()
            st.success("Retrain triggered." if result else "API unavailable.")
            st.session_state["_confirm_retrain"] = False
        else:
            st.session_state["_confirm_retrain"] = True
            st.warning("Click again to confirm.")

    st.markdown("**Leverage**")
    leverage = st.slider("Set Leverage", 1, 10, 3)
    if st.button("Apply Leverage"):
        result = api.post_set_leverage(leverage)
        st.success(f"Leverage set to {leverage}x." if result else "API unavailable.")

with col3:
    st.markdown("**Emergency**")
    st.error("Closes ALL positions immediately.")
    if st.button("EMERGENCY EXIT", type="primary"):
        st.session_state["_confirm_emergency"] = True

    if st.session_state.get("_confirm_emergency"):
        st.error("Confirm: close all positions?")
        cy, cn = st.columns(2)
        with cy:
            if st.button("YES — EXIT ALL"):
                result = api.post_emergency_exit()
                st.success("Done." if result else "API unavailable.")
                st.session_state["_confirm_emergency"] = False
        with cn:
            if st.button("Cancel"):
                st.session_state["_confirm_emergency"] = False
