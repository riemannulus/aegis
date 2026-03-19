"""Page 2: Decision audit trail viewer."""

from __future__ import annotations

import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from backoffice import api_client as api
from backoffice.components.filters import date_range_filter, decision_type_filter
from backoffice.components.charts import bar_chart, pie_chart

st.set_page_config(page_title="Decision Log — Aegis", layout="wide")
st.title("Decision Audit Trail")
st.caption("Why every trade was (or was not) made.")

# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Filters")
    selected_types = decision_type_filter()
    limit = st.number_input("Max records", 10, 1000, 200)

# ---------------------------------------------------------------------------
# Fetch and parse
# ---------------------------------------------------------------------------
decisions_raw = api.get_decisions(limit=int(limit)) or []

rows = []
for d in decisions_raw:
    ts = d.get("timestamp", "")
    try:
        dt = pd.to_datetime(ts)
    except Exception:
        dt = pd.NaT
    rows.append({
        "id": d.get("id", ""),
        "timestamp": dt,
        "decision": d.get("decision", ""),
        "direction": d.get("direction", ""),
        "z_score": d.get("z_score", 0.0),
        "regime": d.get("regime", ""),
        "reason": (d.get("reason") or "")[:80],
        "_full": d.get("full_record", {}),
    })

df = pd.DataFrame(rows)
if not df.empty:
    df = df.sort_values("timestamp", ascending=False)
    if selected_types:
        df = df[df["decision"].isin(selected_types)]

# ---------------------------------------------------------------------------
# Summary stats
# ---------------------------------------------------------------------------
if not df.empty:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total decisions", len(df))
    c2.metric("EXECUTE", int((df["decision"] == "EXECUTE").sum()))
    c3.metric("SKIP", int((df["decision"] == "SKIP").sum()))
    c4.metric("REJECTED", int((df["decision"] == "REJECTED_BY_RISK").sum()))

    type_counts = df["decision"].value_counts().reset_index()
    type_counts.columns = ["decision", "count"]
    st.plotly_chart(
        bar_chart(type_counts, x="decision", y="count", title="Decision Distribution"),
        use_container_width=True,
    )
else:
    st.info("No decisions found.")
    st.stop()

# ---------------------------------------------------------------------------
# Table + detail panel
# ---------------------------------------------------------------------------
st.subheader("Decision Records")
display_df = df[["timestamp", "decision", "direction", "z_score", "regime", "reason"]].copy()
display_df["z_score"] = display_df["z_score"].apply(lambda x: f"{float(x):.2f}" if pd.notna(x) else "")
display_df["timestamp"] = display_df["timestamp"].apply(
    lambda x: x.strftime("%Y-%m-%d %H:%M:%S") if pd.notna(x) else ""
)

sel_result = st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
)

sel_rows = (sel_result or {}).get("selection", {}).get("rows", [])
if sel_rows:
    idx = sel_rows[0]
    record = df.iloc[idx]["_full"]
    row_data = df.iloc[idx]

    st.divider()
    st.subheader(f"Detail: {row_data['decision']} @ {row_data['timestamp']}")

    if isinstance(record, dict) and record:
        tabs = st.tabs(["Model Predictions", "TRA Router", "Top Features", "Risk Check", "Execution"])

        with tabs[0]:
            preds = record.get("model_predictions", {})
            if preds:
                models = ["lgbm", "tra", "adarnn", "ensemble"]
                values = [float(preds.get(m, 0)) for m in models]
                fig = go.Figure(go.Bar(
                    x=[m.upper() for m in models], y=values,
                    marker_color=["#00d4aa", "#f7931a", "#a855f7", "#3b82f6"],
                ))
                fig.update_layout(title="Model Predictions", template="plotly_dark", yaxis_title="Predicted Return")
                st.plotly_chart(fig, use_container_width=True)
                st.metric("Z-Score", f"{preds.get('z_score', 0):.2f}")

        with tabs[1]:
            preds = record.get("model_predictions", {})
            weights = preds.get("tra_router_weights", [])
            active = preds.get("tra_active_router", 0)
            if weights:
                labels = [f"Predictor {i}" for i in range(len(weights))]
                st.plotly_chart(pie_chart(labels, weights, title="TRA Router Weights"), use_container_width=True)
                st.caption(f"Active predictor: #{active}")
            else:
                st.info("No router weight data available.")

        with tabs[2]:
            features = record.get("top_features", [])
            if features:
                st.dataframe(pd.DataFrame(features), use_container_width=True, hide_index=True)
            else:
                st.info("No feature data.")

        with tabs[3]:
            risk = record.get("risk_check", {})
            if risk:
                c1, c2 = st.columns(2)
                with c1:
                    passed = risk.get("stage1_passed", False)
                    st.metric("Stage 1", "PASSED ✓" if passed else "FAILED ✗")
                    st.json(risk.get("stage1_detail", {}))
                with c2:
                    st.metric("Drawdown", f"{risk.get('drawdown_pct', 0):.2f}%")
                    st.metric("Liq Distance", f"{risk.get('liquidation_distance_pct', 0):.1f}%")
                    st.metric("Stop Loss", f"{risk.get('stop_loss_level', 0):.4f}")
                    st.metric("Take Profit", f"{risk.get('take_profit_level', 0):.4f}")

        with tabs[4]:
            execution = record.get("execution")
            if execution:
                st.json(execution)
            else:
                st.info("No execution data (SKIP or REJECTED).")

    # What-if simulator
    st.subheader("What-if: Signal Threshold Simulation")
    current_z = float(row_data["z_score"]) if pd.notna(row_data["z_score"]) else 0.0
    sim_threshold = st.slider("Signal threshold", 0.0, 3.0, 1.0, 0.1)
    if abs(current_z) >= sim_threshold:
        st.success(f"Z={current_z:.2f} >= {sim_threshold} → would **EXECUTE**")
    else:
        st.warning(f"Z={current_z:.2f} < {sim_threshold} → would **SKIP**")
