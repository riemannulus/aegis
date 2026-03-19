"""Aegis Backoffice — Streamlit multi-page app entry point.

Run with:
    streamlit run backoffice/app.py --server.port 8501 --server.baseUrlPath /aegis
"""

import streamlit as st

st.set_page_config(
    page_title="Aegis Backoffice",
    page_icon="🛡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.sidebar.title("Aegis Backoffice")
st.sidebar.caption("AI Crypto Futures Trading System")

st.markdown("""
# Aegis Backoffice Dashboard

Welcome to the Aegis AI trading system backoffice.

Use the **sidebar navigation** to access:

| Page | Description |
|------|-------------|
| 01 Live Dashboard | Real-time system status, current position, equity curve |
| 02 Decision Log | Audit trail — why every trade was (or wasn't) made |
| 03 Trade Journal | Individual trade analysis with candle charts |
| 04 PnL Analytics | Equity curve, drawdown, Sharpe, attribution |
| 05 Model Monitor | IC trend, feature importance, prediction drift |
| 06 Risk Dashboard | Drawdown gauge, risk events, liquidation history |
| 07 Backtest Viewer | Compare backtest runs vs live performance |
| 08 System Ops | Logs, latency waterfall, manual controls |
""")

st.info("Select a page from the sidebar to get started.", icon="ℹ️")
