"""Page 7: Backtest result comparison viewer."""

from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from backoffice import api_client as api
from backoffice.components.charts import equity_curve_chart, drawdown_chart

st.set_page_config(page_title="Backtest Viewer — Aegis", layout="wide")
st.title("Backtest Results Viewer")
st.caption("Compare historical backtest runs vs live trading performance.")

# ---------------------------------------------------------------------------
# Run new backtest
# ---------------------------------------------------------------------------
with st.expander("Run New Backtest", expanded=False):
    with st.form("run_backtest_form"):
        col1, col2 = st.columns(2)
        with col1:
            symbol = st.text_input("Symbol", value="BTC/USDT:USDT")
            interval = st.selectbox("Interval", ["1h", "4h", "1d", "15m"])
            leverage = st.number_input("Leverage", min_value=1, max_value=20, value=3)
        with col2:
            start_date = st.date_input("Start Date")
            end_date = st.date_input("End Date")
            capital = st.number_input("Initial Capital (USDT)", min_value=100, value=10000)
        submitted = st.form_submit_button("Execute Backtest", type="primary")
        if submitted:
            with st.spinner("Triggering backtest run..."):
                result = api.post_run_backtest({
                    "symbol": symbol, "interval": interval,
                    "start": str(start_date), "end": str(end_date),
                    "leverage": leverage, "capital": capital,
                })
            if result and result.get("success"):
                st.success(result.get("message", "Backtest triggered successfully."))
                st.rerun()
            else:
                st.error("Failed to trigger backtest (API unavailable or error).")

st.divider()

# ---------------------------------------------------------------------------
# Load backtest list
# ---------------------------------------------------------------------------
with st.spinner("Loading backtest results..."):
    bt_list = api.get_backtest_list() or []

# Also scan local files as fallback
results_dir = Path("data/backtest_results")
local_files = sorted(results_dir.glob("*.csv")) if results_dir.exists() else []
local_names = [f.stem for f in local_files]

all_runs = [b.get("id", b.get("name", "")) for b in bt_list] + local_names
all_runs = list(dict.fromkeys(all_runs))  # deduplicate, preserve order

if not all_runs:
    st.info("No backtest results found. Use the 'Run New Backtest' form above to generate results.")
    st.stop()

# ---------------------------------------------------------------------------
# Run selector
# ---------------------------------------------------------------------------
selected = st.multiselect("Select backtest runs to compare", all_runs,
                          default=all_runs[:1] if all_runs else [])

if not selected:
    st.info("Select at least one run above.")
    st.stop()

# ---------------------------------------------------------------------------
# Load selected runs
# ---------------------------------------------------------------------------
run_data: dict[str, pd.DataFrame] = {}

for run_id in selected:
    # Try API first
    detail = api.get_backtest_detail(run_id)
    if detail and "trades" in detail:
        df = pd.DataFrame(detail["trades"])
        run_data[run_id] = df
        continue

    # Fallback: local CSV
    local_path = results_dir / f"{run_id}.csv"
    if local_path.exists():
        df = pd.read_csv(local_path)
        run_data[run_id] = df

if not run_data:
    st.warning("Could not load data for selected runs.")
    st.stop()

# ---------------------------------------------------------------------------
# Equity curve overlay
# ---------------------------------------------------------------------------
st.subheader("Equity Curve Comparison")
fig_eq = go.Figure()
for run_id, df in run_data.items():
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    time_col = "timestamp" if "timestamp" in df.columns else df.columns[0]
    pnl_col = "cum_pnl" if "cum_pnl" in df.columns else (
        "net_pnl" if "net_pnl" in df.columns else ("pnl" if "pnl" in df.columns else None)
    )
    if pnl_col:
        if pnl_col != "cum_pnl":
            df = df.sort_values(time_col)
            df["cum_pnl"] = df[pnl_col].cumsum()
        fig_eq.add_trace(go.Scatter(x=df[time_col], y=df["cum_pnl"], mode="lines", name=run_id))

fig_eq.update_layout(title="Cumulative PnL — All Selected Runs",
                     template="plotly_dark", xaxis_title="Time", yaxis_title="Cumulative PnL (USDT)",
                     margin=dict(l=40, r=20, t=60, b=40))
st.plotly_chart(fig_eq, use_container_width=True)

# ---------------------------------------------------------------------------
# Per-run summary metrics
# ---------------------------------------------------------------------------
st.subheader("Run Comparison Table")
summary_rows = []
for run_id, df in run_data.items():
    pnl_col = "net_pnl" if "net_pnl" in df.columns else ("pnl" if "pnl" in df.columns else None)
    if pnl_col:
        pnl = df[pnl_col]
        summary_rows.append({
            "Run": run_id,
            "Trades": len(df),
            "Total PnL": f"${pnl.sum():.2f}",
            "Win Rate": f"{(pnl > 0).mean():.1%}",
            "Avg PnL": f"${pnl.mean():.2f}",
            "Max Loss": f"${pnl.min():.2f}",
            "Best Trade": f"${pnl.max():.2f}",
        })

if summary_rows:
    st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Detailed view for single selected run
# ---------------------------------------------------------------------------
if len(selected) == 1:
    run_id = selected[0]
    df = run_data.get(run_id, pd.DataFrame())
    if not df.empty:
        st.subheader(f"Details: {run_id}")

        # Drawdown
        pnl_col = "net_pnl" if "net_pnl" in df.columns else ("pnl" if "pnl" in df.columns else None)
        if pnl_col:
            df_s = df.sort_values("timestamp" if "timestamp" in df.columns else df.columns[0])
            df_s["cum_pnl"] = df_s[pnl_col].cumsum()
            df_s["equity"] = 10000 + df_s["cum_pnl"]
            time_col = "timestamp" if "timestamp" in df_s.columns else df_s.columns[0]
            df_s = df_s.rename(columns={time_col: "timestamp"})
            st.plotly_chart(drawdown_chart(df_s), use_container_width=True)

        # Trade list
        st.subheader("Trade List")
        st.dataframe(df, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Live vs backtest comparison
# ---------------------------------------------------------------------------
st.subheader("Live vs Backtest")
equity_data = api.get_equity_curve() or []
if equity_data and run_data:
    live_df = pd.DataFrame(equity_data)
    if "timestamp" not in live_df.columns and "exit_time" in live_df.columns:
        live_df = live_df.rename(columns={"exit_time": "timestamp"})
    live_df["timestamp"] = pd.to_datetime(live_df["timestamp"])

    fig_comp = go.Figure()
    fig_comp.add_trace(go.Scatter(x=live_df["timestamp"], y=live_df.get("equity", live_df.get("cum_pnl", [])),
                                  mode="lines", name="Live", line=dict(color="#00d4aa", width=2)))

    first_run = list(run_data.values())[0]
    first_run_id = list(run_data.keys())[0]
    time_col = "timestamp" if "timestamp" in first_run.columns else first_run.columns[0]
    pnl_col = "cum_pnl" if "cum_pnl" in first_run.columns else (
        "net_pnl" if "net_pnl" in first_run.columns else None)
    if pnl_col:
        first_run = first_run.sort_values(time_col)
        if pnl_col != "cum_pnl":
            first_run["cum_pnl"] = first_run[pnl_col].cumsum()
        fig_comp.add_trace(go.Scatter(x=first_run[time_col], y=first_run["cum_pnl"],
                                      mode="lines", name=f"Backtest: {first_run_id}",
                                      line=dict(color="#f7931a", dash="dash")))

    fig_comp.update_layout(title="Live Performance vs Backtest",
                           template="plotly_dark", xaxis_title="Time",
                           yaxis_title="Cumulative PnL (USDT)",
                           margin=dict(l=40, r=20, t=60, b=40))
    st.plotly_chart(fig_comp, use_container_width=True)
    st.caption("Large divergence between live and backtest may indicate overfitting or regime change.")
else:
    st.info("Connect API and select a backtest run to compare live vs backtest.")
