"""Page 3: Trade journal — individual trade analysis."""

from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import pandas as pd
import plotly.express as px
import streamlit as st

from backoffice import api_client as api
from backoffice.components.filters import date_range_filter, direction_filter, result_filter
from backoffice.components.charts import candlestick_chart

st.set_page_config(page_title="Trade Journal — Aegis", layout="wide")
st.title("Trade Journal")

# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Filters")
    start_date, end_date = date_range_filter("trade", default_days=30)
    directions = direction_filter()
    results = result_filter()

# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------
trades_raw = api.get_trades(limit=500) or []

if not trades_raw:
    st.info("No trades recorded yet.")
    st.stop()

df = pd.DataFrame(trades_raw)

# Normalise columns
for col in ["entry_time", "exit_time", "timestamp"]:
    if col in df.columns:
        df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)

if "timestamp" in df.columns and "exit_time" not in df.columns:
    df["exit_time"] = df["timestamp"]

# Direction label
if "direction" in df.columns:
    df["direction_label"] = df["direction"].map({1: "LONG", -1: "SHORT"}).fillna(df.get("side", ""))
elif "side" in df.columns:
    df["direction_label"] = df["side"].str.upper()
else:
    df["direction_label"] = "UNKNOWN"

if "pnl" not in df.columns and "net_pnl" in df.columns:
    df["pnl"] = df["net_pnl"]
elif "pnl" not in df.columns:
    df["pnl"] = 0.0

df["result"] = df["pnl"].apply(lambda x: "WIN" if x > 0 else "LOSS")

# Apply filters
if directions:
    df = df[df["direction_label"].isin(directions)]
if results:
    df = df[df["result"].isin(results)]

if df.empty:
    st.info("No trades match the current filters.")
    st.stop()

# ---------------------------------------------------------------------------
# Summary metrics
# ---------------------------------------------------------------------------
total = len(df)
wins = (df["pnl"] > 0).sum()
win_rate = wins / total if total > 0 else 0.0
total_pnl = df["pnl"].sum()
avg_pnl = df["pnl"].mean()
total_funding = df["funding_cost"].sum() if "funding_cost" in df.columns else 0.0

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total Trades", total)
c2.metric("Win Rate", f"{win_rate:.1%}")
c3.metric("Total Net PnL", f"${total_pnl:+.2f}")
c4.metric("Avg PnL/Trade", f"${avg_pnl:+.2f}")
c5.metric("Total Funding Cost", f"${total_funding:.2f}")

# ---------------------------------------------------------------------------
# Cumulative PnL chart
# ---------------------------------------------------------------------------
_sort_col = "exit_time" if "exit_time" in df.columns else ("timestamp" if "timestamp" in df.columns else None)
df_sorted = df.sort_values(_sort_col) if _sort_col else df.copy()
df_sorted["cum_pnl"] = df_sorted["pnl"].cumsum()
time_col = _sort_col if _sort_col and _sort_col in df_sorted.columns else None
if time_col and not df_sorted.empty:
    fig_eq = px.line(df_sorted, x=time_col, y="cum_pnl", title="Cumulative PnL",
                     template="plotly_dark")
    st.plotly_chart(fig_eq, use_container_width=True)

# ---------------------------------------------------------------------------
# Trade table
# ---------------------------------------------------------------------------
st.subheader("Trade History")
show_cols = [c for c in ["exit_time", "direction_label", "entry_price", "exit_price",
                          "pnl", "funding_cost", "result"] if c in df_sorted.columns]
display_df = df_sorted[show_cols].sort_values("exit_time" if "exit_time" in show_cols else show_cols[0],
                                               ascending=False)

sel_result = st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
)

# ---------------------------------------------------------------------------
# Individual trade detail
# ---------------------------------------------------------------------------
sel_rows = (sel_result or {}).get("selection", {}).get("rows", [])
if sel_rows:
    idx = sel_rows[0]
    trade = df_sorted.iloc[-(idx + 1)]  # display is descending

    st.divider()
    entry_t = trade.get("entry_time") if "entry_time" in trade.index else None
    exit_t = trade.get("exit_time") if "exit_time" in trade.index else None
    entry_p = float(trade.get("entry_price", 0))
    exit_p = float(trade.get("exit_price", 0))
    direction = trade.get("direction_label", "")
    pnl_val = float(trade.get("pnl", 0))
    funding = float(trade.get("funding_cost", 0)) if "funding_cost" in trade.index else 0.0

    st.subheader(f"Trade Detail — {direction} | PnL: ${pnl_val:+.2f}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Entry", f"${entry_p:,.2f}")
    c2.metric("Exit", f"${exit_p:,.2f}")
    c3.metric("Net PnL", f"${pnl_val:+.2f}")
    c4.metric("Funding Cost", f"${funding:.4f}")

    # Candle chart for the trade window
    if entry_t is not None and exit_t is not None:
        st.caption("Fetching candles for trade window...")
        # Use API or show a placeholder
        st.info("Candle chart: connect to API /candles endpoint to render entry/exit markers.")

    # Notes
    st.subheader("Trade Notes")
    note_key = f"note_{idx}"
    note = st.text_area("Add a memo for this trade:", key=note_key, height=80)
    if st.button("Save Note", key=f"save_{idx}"):
        st.success("Note saved (stored in session state — integrate with DB for persistence).")
