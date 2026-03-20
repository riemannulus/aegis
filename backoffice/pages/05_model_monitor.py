"""Page 5: Model performance monitoring — IC trend, feature importance, prediction drift."""

from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from backoffice import api_client as api
from backoffice.components.charts import ic_trend_chart, bar_chart, pie_chart

st.set_page_config(page_title="Model Monitor — Aegis", layout="wide")
st.title("Model Performance Monitor")
st.caption("Early detection of model staleness and performance degradation.")

# ---------------------------------------------------------------------------
# Sidebar: Training Controls
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Training Controls")
    if st.button("Force Retrain", type="primary", use_container_width=True):
        with st.spinner("Triggering retraining..."):
            result = api.post_force_retrain()
        if result:
            st.success(f"Retrain triggered: {result.get('message', 'OK')}")
        else:
            st.error("Failed to trigger retrain (API unavailable)")

    st.divider()
    st.subheader("Ensemble Parameters")
    st.caption("Reference values (read-only)")
    st.metric("num_leaves", 31)
    st.metric("n_estimators", 100)
    st.metric("n_folds", 5)

# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------
with st.spinner("Loading model metrics..."):
    model_metrics = api.get_model_metrics() or {}

# ---------------------------------------------------------------------------
# Retrain schedule
# ---------------------------------------------------------------------------
st.subheader("Retrain Schedule")
c1, c2, c3 = st.columns(3)
c1.metric("Last Retrain", model_metrics.get("last_retrain_at", "N/A"))
c2.metric("Next Retrain", model_metrics.get("next_retrain_at", "N/A"))
model_files = model_metrics.get("model_files", [])
c3.metric("Saved Model Files", len(model_files))

if model_files:
    with st.expander("Saved model files"):
        st.write(model_files)

# ---------------------------------------------------------------------------
# IC trends
# ---------------------------------------------------------------------------
st.subheader("IC (Information Coefficient) Trend")
ic_history = model_metrics.get("ic_history", [])
if ic_history:
    ic_df = pd.DataFrame(ic_history)
    ic_df["date"] = pd.to_datetime(ic_df.get("date", ic_df.index))
    st.plotly_chart(ic_trend_chart(ic_df, title="Rolling IC by Model"), use_container_width=True)

    # Stale warning
    latest_ic = ic_df.iloc[-1] if not ic_df.empty else {}
    for model in ["lgbm", "tra", "adarnn", "ensemble"]:
        if model in ic_df.columns:
            recent_mean = float(ic_df[model].tail(7).mean())
            if recent_mean < 0:
                st.warning(f"Model **{model.upper()}** has negative IC over the last 7 days — possible staleness!")
else:
    st.info("No IC history from API. Showing saved model files.")
    saved_dir = Path("models/saved")
    if saved_dir.exists():
        files = sorted(saved_dir.iterdir())
        if files:
            model_info = [
                {"name": f.name, "size_kb": f"{f.stat().st_size/1024:.1f}" if f.is_file() else "dir",
                 "modified": pd.Timestamp(f.stat().st_mtime, unit="s").strftime("%Y-%m-%d %H:%M")}
                for f in files
            ]
            st.dataframe(pd.DataFrame(model_info), use_container_width=True, hide_index=True)
        else:
            st.info("No saved model files.")

# ---------------------------------------------------------------------------
# Rank IC
# ---------------------------------------------------------------------------
rank_ic_history = model_metrics.get("rank_ic_history", [])
if rank_ic_history:
    st.subheader("Rank IC Trend")
    ric_df = pd.DataFrame(rank_ic_history)
    ric_df["date"] = pd.to_datetime(ric_df.get("date", ric_df.index))
    st.plotly_chart(ic_trend_chart(ric_df, title="Rolling Rank IC by Model"), use_container_width=True)

# ---------------------------------------------------------------------------
# Direction accuracy
# ---------------------------------------------------------------------------
st.subheader("Direction Accuracy by Model")
dir_acc = model_metrics.get("direction_accuracy", {})
if dir_acc:
    acc_df = pd.DataFrame([{"model": k, "accuracy": v} for k, v in dir_acc.items()])
    fig = px.bar(acc_df, x="model", y="accuracy", title="Direction Accuracy",
                 template="plotly_dark", color="accuracy",
                 color_continuous_scale="RdYlGn", range_color=[0.4, 0.7])
    fig.add_hline(y=0.5, line_dash="dash", line_color="gray", annotation_text="50% baseline")
    st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------------------
# Feature importance
# ---------------------------------------------------------------------------
st.subheader("Feature Importance")
feat_importance = model_metrics.get("feature_importance", {})
if feat_importance:
    tabs = st.tabs(list(feat_importance.keys()))
    for tab, model_name in zip(tabs, feat_importance.keys()):
        with tab:
            fi = feat_importance[model_name]
            fi_df = pd.DataFrame(list(fi.items()), columns=["feature", "importance"])
            fi_df = fi_df.sort_values("importance", ascending=False).head(20)
            fig = px.bar(fi_df, x="importance", y="feature", orientation="h",
                         title=f"{model_name.upper()} Feature Importance (Top 20)",
                         template="plotly_dark")
            st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No feature importance data from API.")

# ---------------------------------------------------------------------------
# Prediction distribution drift
# ---------------------------------------------------------------------------
st.subheader("Prediction Distribution (KL-Divergence Alert)")
pred_dist = model_metrics.get("prediction_distribution_drift", {})
if pred_dist:
    for model_name, kl_div in pred_dist.items():
        level = "normal" if kl_div < 0.1 else ("warning" if kl_div < 0.3 else "critical")
        icon = {"normal": "✅", "warning": "⚠️", "critical": "🚨"}[level]
        st.metric(f"{icon} {model_name.upper()} KL-Divergence", f"{kl_div:.4f}")

# ---------------------------------------------------------------------------
# TRA router activity
# ---------------------------------------------------------------------------
st.subheader("TRA Router Predictor Activity")
router_activity = model_metrics.get("tra_router_activity", [])
if router_activity:
    ra_df = pd.DataFrame(router_activity)
    if "predictor" in ra_df.columns and "frequency" in ra_df.columns:
        st.plotly_chart(
            pie_chart(ra_df["predictor"].tolist(), ra_df["frequency"].tolist(),
                      title="TRA Router: Predictor Selection Frequency"),
            use_container_width=True,
        )

        if "date" in ra_df.columns:
            fig = px.line(ra_df, x="date", y="frequency", color="predictor",
                          title="Router Activity Over Time", template="plotly_dark")
            st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No TRA router activity data.")

# ---------------------------------------------------------------------------
# Ensemble vs individual comparison
# ---------------------------------------------------------------------------
st.subheader("Ensemble vs Individual Model IC")
ensemble_comparison = model_metrics.get("ensemble_vs_individual", {})
if ensemble_comparison:
    comp_df = pd.DataFrame([{"model": k, "IC": v} for k, v in ensemble_comparison.items()])
    fig = px.bar(comp_df, x="model", y="IC", title="Ensemble vs Individual IC",
                 template="plotly_dark", color="IC",
                 color_continuous_scale="RdYlGn", color_continuous_midpoint=0)
    st.plotly_chart(fig, use_container_width=True)
