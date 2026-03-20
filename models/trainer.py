"""Model training and retraining pipeline for Aegis trading system.

Public API
----------
train_all_models(X, y, val_ratio, save_dir, **kwargs)
    Train LightGBM, TRA, and ADARNN + ensemble on the provided dataset.

retrain_rolling(get_data_fn, save_dir, window_days, retrain_days, **kwargs)
    Rolling retraining loop: every `retrain_days` days, pull the latest
    `window_days` of data and retrain all models.

evaluate(model, X, y, feature_names)
    Compute IC, Rank IC, direction accuracy, and Sharpe ratio.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

import numpy as np
from scipy.stats import spearmanr

from models.lgbm_model import LGBMModel
from models.tra_model import TRAModel
from models.adarnn_model import AdaRNNModel
from models.ensemble import EnsembleModel
from models.base import BaseModel

logger = logging.getLogger(__name__)

# Defaults
_WINDOW_DAYS = 90
_RETRAIN_DAYS = 7
_VAL_RATIO = 0.1          # last 10% of window used for validation


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def evaluate(
    model: BaseModel,
    X: np.ndarray,
    y: np.ndarray,
    feature_names: Optional[list[str]] = None,
) -> dict:
    """Compute evaluation metrics for a trained model.

    Returns
    -------
    dict with keys: IC, Rank_IC, direction_accuracy, sharpe
    """
    preds = model.predict(X)

    # Drop NaN positions (TRA/ADARNN pad with NaN at the start)
    valid = np.isfinite(preds) & np.isfinite(y)
    if valid.sum() < 10:
        logger.warning("evaluate(): fewer than 10 valid predictions — metrics unreliable")
        return {"IC": float("nan"), "Rank_IC": float("nan"),
                "direction_accuracy": float("nan"), "sharpe": float("nan")}

    p, t = preds[valid], y[valid]

    ic = float(np.corrcoef(p, t)[0, 1])
    rank_ic, _ = spearmanr(p, t)
    direction_accuracy = float(np.mean(np.sign(p) == np.sign(t)))

    # Sharpe: treat each prediction as a daily return signal
    # position = sign(prediction); return = position * actual_return
    strategy_returns = np.sign(p) * t
    sharpe = float(
        np.mean(strategy_returns) / (np.std(strategy_returns) + 1e-9) * np.sqrt(252)
    )

    metrics = {
        "IC": round(ic, 6),
        "Rank_IC": round(float(rank_ic), 6),
        "direction_accuracy": round(direction_accuracy, 4),
        "sharpe": round(sharpe, 4),
    }
    logger.info("Evaluation metrics: %s", metrics)
    return metrics


def train_all_models(
    X: np.ndarray,
    y: np.ndarray,
    val_ratio: float = _VAL_RATIO,
    save_dir: str = "models/saved",
    feature_names: Optional[list[str]] = None,
    lgbm_kwargs: Optional[dict] = None,
    tra_kwargs: Optional[dict] = None,
    adarnn_kwargs: Optional[dict] = None,
    train_ensemble: bool = True,
) -> dict[str, BaseModel]:
    """Train all base models sequentially and optionally the ensemble.

    Parameters
    ----------
    X : np.ndarray
        Feature matrix, shape (n_samples, n_features).
    y : np.ndarray
        Return targets, shape (n_samples,).
    val_ratio : float
        Fraction of the dataset used for validation (time-based split).
    save_dir : str
        Directory where versioned model artefacts are written.
    feature_names : list[str] or None
        Column names for the feature matrix.
    lgbm_kwargs / tra_kwargs / adarnn_kwargs : dict or None
        Override hyperparameters for each base model.
    train_ensemble : bool
        Whether to train the stacking ensemble on top.

    Returns
    -------
    dict mapping model name → trained model instance.
    """
    os.makedirs(save_dir, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

    split = int(len(X) * (1 - val_ratio))
    X_train, y_train = X[:split], y[:split]
    X_val, y_val = X[split:], y[split:]

    logger.info(
        "train_all_models: n_train=%d, n_val=%d, n_features=%d",
        len(X_train), len(X_val), X.shape[1],
    )

    models: dict[str, BaseModel] = {}

    # --- LightGBM ---
    logger.info("Training LightGBM …")
    lgbm = LGBMModel(feature_names=feature_names, **(lgbm_kwargs or {}))
    lgbm.train(X_train, y_train, X_val, y_val)
    lgbm_path = os.path.join(save_dir, f"lgbm_{timestamp}.lgbm")
    lgbm.save(lgbm_path)
    models["lgbm"] = lgbm
    logger.info("LightGBM metrics: %s", evaluate(lgbm, X_val, y_val, feature_names))

    # --- TRA ---
    logger.info("Training TRA …")
    tra = TRAModel(**(tra_kwargs or {}))
    tra.train(X_train, y_train, X_val, y_val)
    tra_path = os.path.join(save_dir, f"tra_{timestamp}.pt")
    tra.save(tra_path)
    models["tra"] = tra
    logger.info("TRA metrics: %s", evaluate(tra, X_val, y_val))

    # --- ADARNN ---
    logger.info("Training ADARNN …")
    adarnn = AdaRNNModel(**(adarnn_kwargs or {}))
    adarnn.train(X_train, y_train, X_val, y_val)
    adarnn_path = os.path.join(save_dir, f"adarnn_{timestamp}.pt")
    adarnn.save(adarnn_path)
    models["adarnn"] = adarnn
    logger.info("ADARNN metrics: %s", evaluate(adarnn, X_val, y_val))

    # --- Ensemble ---
    if train_ensemble:
        logger.info("Training Ensemble …")
        ensemble = EnsembleModel(
            lgbm_kwargs=lgbm_kwargs or {},
            tra_kwargs=tra_kwargs or {},
            adarnn_kwargs=adarnn_kwargs or {},
        )
        ensemble.train(X_train, y_train, X_val, y_val)
        ens_dir = os.path.join(save_dir, f"ensemble_{timestamp}")
        ensemble.save(ens_dir)
        # Also save to stable path so orchestrator can find the latest ensemble
        stable_dir = os.path.join(save_dir, "ensemble")
        ensemble.save(stable_dir)
        models["ensemble"] = ensemble
        logger.info("Ensemble metrics: %s", evaluate(ensemble, X_val, y_val))

    return models


# ---------------------------------------------------------------------------
# Rolling retrain
# ---------------------------------------------------------------------------

def retrain_rolling(
    get_data_fn: Callable[[datetime, datetime], tuple[np.ndarray, np.ndarray]],
    save_dir: str = "models/saved",
    window_days: int = _WINDOW_DAYS,
    retrain_days: int = _RETRAIN_DAYS,
    val_ratio: float = _VAL_RATIO,
    feature_names: Optional[list[str]] = None,
    lgbm_kwargs: Optional[dict] = None,
    tra_kwargs: Optional[dict] = None,
    adarnn_kwargs: Optional[dict] = None,
    num_cycles: Optional[int] = None,
) -> None:
    """Simulate rolling retraining cycles.

    Parameters
    ----------
    get_data_fn : Callable[[datetime, datetime], (X, y)]
        Function that returns (X, y) for the given date range.
    window_days : int
        Length of the rolling training window in days (default 90).
    retrain_days : int
        How often to retrain in days (default 7 = weekly).
    num_cycles : int or None
        If provided, run at most this many retrain cycles (useful for testing).
    """
    now = datetime.now(timezone.utc)
    end = now
    start = end - timedelta(days=window_days)
    cycle = 0

    while True:
        if num_cycles is not None and cycle >= num_cycles:
            break

        logger.info(
            "retrain_rolling cycle=%d | window=%s → %s",
            cycle, start.date(), end.date(),
        )

        try:
            X, y = get_data_fn(start, end)
            if len(X) < 100:
                logger.warning("Insufficient data for retraining (%d rows), skipping.", len(X))
            else:
                train_all_models(
                    X, y,
                    val_ratio=val_ratio,
                    save_dir=save_dir,
                    feature_names=feature_names,
                    lgbm_kwargs=lgbm_kwargs,
                    tra_kwargs=tra_kwargs,
                    adarnn_kwargs=adarnn_kwargs,
                )
        except Exception:
            logger.exception("retrain_rolling cycle=%d failed", cycle)

        cycle += 1
        # Advance window
        start += timedelta(days=retrain_days)
        end += timedelta(days=retrain_days)

        # If we've caught up to the future, stop the simulation
        if start >= now:
            break


# ---------------------------------------------------------------------------
# OOP wrapper used by scheduler.orchestrator
# ---------------------------------------------------------------------------

class ModelTrainer:
    """Thin class wrapper around the module-level training functions.

    The orchestrator instantiates ``ModelTrainer(storage=...)`` and calls
    ``retrain_rolling()`` on the scheduler's 7-day interval.
    """

    def __init__(self, storage=None, save_dir: str = "models/saved"):
        self.storage = storage
        self.save_dir = save_dir
        self._models: dict[str, BaseModel] = {}

    def retrain_rolling(
        self,
        window_days: int = _WINDOW_DAYS,
        retrain_days: int = _RETRAIN_DAYS,
    ) -> None:
        """Pull recent data from storage and retrain all models."""

        def _get_data(start_dt, end_dt):
            if self.storage is None:
                return np.empty((0, 0)), np.empty(0)
            start_ms = int(start_dt.timestamp() * 1000)
            end_ms = int(end_dt.timestamp() * 1000)
            rows = self.storage.get_candles(
                symbol="BTCUSDT", interval="30m",
                start_ts=start_ms, end_ts=end_ms,
            )
            if not rows:
                return np.empty((0, 0)), np.empty(0)
            closes = np.array([r["close"] for r in rows], dtype=np.float64)
            # Use close-to-close returns as targets
            y = np.diff(closes) / (closes[:-1] + 1e-9)
            # Simple feature matrix from OHLCV columns
            feature_keys = ["open", "high", "low", "close", "volume"]
            X = np.array(
                [[r.get(k, 0.0) for k in feature_keys] for r in rows[:-1]],
                dtype=np.float64,
            )
            return X, y

        retrain_rolling(
            get_data_fn=_get_data,
            save_dir=self.save_dir,
            window_days=window_days,
            retrain_days=retrain_days,
        )

    def train_all(self, X, y, val_ratio=_VAL_RATIO):
        """Train all models on the provided dataset."""
        return train_all_models(X, y, val_ratio=val_ratio, save_dir=self.save_dir)

    def load_all_models(self) -> None:
        """Scan save_dir and load the latest version of each model type."""
        import glob

        if not os.path.isdir(self.save_dir):
            logger.warning("load_all_models: save_dir %s does not exist", self.save_dir)
            return

        # --- LightGBM: latest *.lgbm file ---
        lgbm_files = sorted(glob.glob(os.path.join(self.save_dir, "*.lgbm")))
        if lgbm_files:
            try:
                m = LGBMModel()
                m.load(lgbm_files[-1])
                self._models["lgbm"] = m
                logger.info("Loaded lgbm from %s", lgbm_files[-1])
            except Exception as exc:
                logger.warning("Failed to load lgbm: %s", exc)

        # --- TRA: latest *tra*.pt file ---
        tra_files = sorted(glob.glob(os.path.join(self.save_dir, "*tra*.pt")))
        if tra_files:
            try:
                m = TRAModel()
                m.load(tra_files[-1])
                self._models["tra"] = m
                logger.info("Loaded tra from %s", tra_files[-1])
            except Exception as exc:
                logger.warning("Failed to load tra: %s", exc)

        # --- ADARNN: latest *adarnn*.pt file ---
        adarnn_files = sorted(glob.glob(os.path.join(self.save_dir, "*adarnn*.pt")))
        if adarnn_files:
            try:
                m = AdaRNNModel()
                m.load(adarnn_files[-1])
                self._models["adarnn"] = m
                logger.info("Loaded adarnn from %s", adarnn_files[-1])
            except Exception as exc:
                logger.warning("Failed to load adarnn: %s", exc)

        # --- Ensemble: latest ensemble_* directory ---
        ens_dirs = sorted([
            d for d in glob.glob(os.path.join(self.save_dir, "ensemble_*"))
            if os.path.isdir(d)
        ])
        if ens_dirs:
            try:
                m = EnsembleModel()
                m.load(ens_dirs[-1])
                self._models["ensemble"] = m
                logger.info("Loaded ensemble from %s", ens_dirs[-1])
            except Exception as exc:
                logger.warning("Failed to load ensemble: %s", exc)

        logger.info("load_all_models: loaded %d model(s): %s", len(self._models), list(self._models.keys()))

    def predict_all(self, X: np.ndarray) -> dict:
        """Run prediction through all loaded models.

        Returns dict with keys: lgbm, tra, adarnn, ensemble, tra_router_weights.
        Missing or failing models return 0.0 gracefully.
        """
        result: dict = {
            "lgbm": 0.0,
            "tra": 0.0,
            "adarnn": 0.0,
            "ensemble": 0.0,
            "tra_router_weights": [0.33, 0.33, 0.34],
        }

        for name in ("lgbm", "tra", "adarnn", "ensemble"):
            model = self._models.get(name)
            if model is None:
                continue
            try:
                preds = model.predict(X)
                valid = preds[np.isfinite(preds)]
                result[name] = float(valid[-1]) if len(valid) > 0 else 0.0
            except Exception as exc:
                logger.debug("predict_all[%s] failed: %s", name, exc)

        # TRA router weights for regime detection
        tra_model = self._models.get("tra")
        if tra_model is not None and hasattr(tra_model, "get_router_weights"):
            try:
                weights = tra_model.get_router_weights(X)
                if weights is not None and len(weights) > 0:
                    result["tra_router_weights"] = weights.tolist()
            except Exception as exc:
                logger.debug("predict_all[tra_router_weights] failed: %s", exc)

        return result

    def get_model_metrics(self) -> dict:
        """Return dict with model file info and lgbm feature importance."""
        import glob

        metrics: dict = {
            "last_retrain_at": None,
            "models_loaded": list(self._models.keys()),
            "model_files": {},
            "feature_importance": {},
        }

        if not os.path.isdir(self.save_dir):
            return metrics

        for pattern, key in [("*.lgbm", "lgbm"), ("*tra*.pt", "tra"), ("*adarnn*.pt", "adarnn")]:
            files = sorted(glob.glob(os.path.join(self.save_dir, pattern)))
            if files:
                latest = files[-1]
                mtime = os.path.getmtime(latest)
                mtime_str = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
                metrics["model_files"][key] = {"path": latest, "modified": mtime_str}
                if metrics["last_retrain_at"] is None or mtime_str > metrics["last_retrain_at"]:
                    metrics["last_retrain_at"] = mtime_str

        ens_dirs = sorted([
            d for d in glob.glob(os.path.join(self.save_dir, "ensemble_*"))
            if os.path.isdir(d)
        ])
        if ens_dirs:
            latest = ens_dirs[-1]
            mtime = os.path.getmtime(latest)
            mtime_str = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
            metrics["model_files"]["ensemble"] = {"path": latest, "modified": mtime_str}

        lgbm_model = self._models.get("lgbm")
        if lgbm_model is not None and hasattr(lgbm_model, "get_feature_importance"):
            try:
                metrics["feature_importance"] = lgbm_model.get_feature_importance()
            except Exception:
                pass

        return metrics
