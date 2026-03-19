"""Stacking ensemble model for Aegis trading system.

Uses time-based 5-fold CV to generate out-of-fold predictions from
LGBMModel, TRAModel, and AdaRNNModel, then trains a small LightGBM
meta-model on those OOF predictions.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import lightgbm as lgb
import numpy as np
from scipy.stats import spearmanr

from models.base import BaseModel
from models.lgbm_model import LGBMModel
from models.tra_model import TRAModel
from models.adarnn_model import AdaRNNModel

logger = logging.getLogger(__name__)


class EnsembleModel(BaseModel):
    """Stacking ensemble: LightGBM + TRA + ADARNN → meta LightGBM.

    Parameters
    ----------
    n_folds : int
        Number of time-based CV folds (default 5).
    lgbm_kwargs : dict
        Kwargs forwarded to LGBMModel constructor.
    tra_kwargs : dict
        Kwargs forwarded to TRAModel constructor.
    adarnn_kwargs : dict
        Kwargs forwarded to AdaRNNModel constructor.
    meta_num_leaves : int
        num_leaves for the meta LightGBM model.
    meta_n_estimators : int
        n_estimators for the meta LightGBM model.
    """

    def __init__(
        self,
        n_folds: int = 5,
        lgbm_kwargs: Optional[dict] = None,
        tra_kwargs: Optional[dict] = None,
        adarnn_kwargs: Optional[dict] = None,
        meta_num_leaves: int = 8,
        meta_n_estimators: int = 50,
    ) -> None:
        self.n_folds = n_folds
        self.lgbm_kwargs = lgbm_kwargs or {}
        self.tra_kwargs = tra_kwargs or {}
        self.adarnn_kwargs = adarnn_kwargs or {}
        self.meta_num_leaves = meta_num_leaves
        self.meta_n_estimators = meta_n_estimators

        # Final base models trained on full training data
        self._lgbm: Optional[LGBMModel] = None
        self._tra: Optional[TRAModel] = None
        self._adarnn: Optional[AdaRNNModel] = None
        # Meta model trained on stacked predictions
        self._meta: Optional[LGBMModel] = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _time_folds(self, n: int) -> list[tuple[np.ndarray, np.ndarray]]:
        """Generate time-based (train_idx, val_idx) pairs.

        Fold i uses samples [0 … (i+1)*chunk] as train and the next chunk as val.
        This mirrors the spec's expanding-window approach.
        """
        chunk = n // (self.n_folds + 1)
        folds = []
        for i in range(self.n_folds):
            train_end = (i + 1) * chunk
            val_end = min(train_end + chunk, n)
            train_idx = np.arange(0, train_end)
            val_idx = np.arange(train_end, val_end)
            if len(train_idx) > 0 and len(val_idx) > 0:
                folds.append((train_idx, val_idx))
        return folds

    def _predict_base(
        self,
        model: BaseModel,
        X: np.ndarray,
    ) -> np.ndarray:
        """Get predictions, replacing NaN with 0."""
        preds = model.predict(X)
        return np.where(np.isfinite(preds), preds, 0.0)

    # ------------------------------------------------------------------
    # BaseModel interface
    # ------------------------------------------------------------------

    def train(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
    ) -> None:
        """Train the meta model on pre-computed stacked predictions (meta features).

        X_train and X_val should be arrays of shape (n_samples, n_base_models)
        containing base model predictions stacked as columns.
        """
        logger.info("Training ensemble meta model on %d samples", len(X_train))
        self._meta = LGBMModel(
            num_leaves=self.meta_num_leaves,
            n_estimators=self.meta_n_estimators,
        )
        self._meta.train(X_train, y_train, X_val, y_val)

        ens_preds = self._meta.predict(X_val)
        ens_ic = float(np.corrcoef(ens_preds, y_val)[0, 1])
        ens_rank_ic, _ = spearmanr(ens_preds, y_val)
        logger.info(
            "Ensemble training complete | ensemble_IC=%.4f | Rank_IC=%.4f",
            ens_ic, ens_rank_ic,
        )

    def _build_val_meta(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
    ) -> np.ndarray:
        """Train quick base models and predict on val to form meta features."""
        meta = np.zeros((len(X_val), 3), dtype=np.float64)

        lgbm = LGBMModel(**self.lgbm_kwargs)
        lgbm.train(X_train, y_train, X_val, y_val)
        meta[:, 0] = lgbm.predict(X_val)

        tra = TRAModel(**self.tra_kwargs)
        tra.train(X_train, y_train, X_val, y_val)
        raw = self._predict_base(tra, X_val)
        meta[:, 1] = raw[-len(X_val):]

        adarnn = AdaRNNModel(**self.adarnn_kwargs)
        adarnn.train(X_train, y_train, X_val, y_val)
        raw = self._predict_base(adarnn, X_val)
        meta[:, 2] = raw[-len(X_val):]

        return meta

    def _make_meta_features(self, X: np.ndarray) -> np.ndarray:
        assert self._lgbm and self._tra and self._adarnn, "Base models not trained."
        meta = np.zeros((len(X), 3), dtype=np.float64)
        meta[:, 0] = self._lgbm.predict(X)
        raw_tra = self._predict_base(self._tra, X)
        meta[:, 1] = raw_tra[-len(X):]
        raw_ada = self._predict_base(self._adarnn, X)
        meta[:, 2] = raw_ada[-len(X):]
        return meta

    def predict(self, X: np.ndarray) -> np.ndarray:
        if self._meta is None:
            raise RuntimeError("Ensemble not trained. Call train() or load() first.")
        return self._meta.predict(X)

    def get_base_predictions(self, X: np.ndarray) -> dict[str, np.ndarray]:
        """Return individual model predictions for inspection/attribution."""
        assert self._lgbm and self._tra and self._adarnn, "Base models not trained."
        return {
            "lgbm": self._lgbm.predict(X),
            "tra": self._predict_base(self._tra, X),
            "adarnn": self._predict_base(self._adarnn, X),
        }

    def save(self, path: str) -> None:
        """Save ensemble to a directory (path is a directory, not a file)."""
        if self._meta is None:
            raise RuntimeError("Ensemble not trained.")
        os.makedirs(path, exist_ok=True)
        self._meta.save(os.path.join(path, "meta.pkl"))
        if self._lgbm is not None:
            self._lgbm.save(os.path.join(path, "lgbm.pkl"))
        if self._tra is not None:
            self._tra.save(os.path.join(path, "tra.pt"))
        if self._adarnn is not None:
            self._adarnn.save(os.path.join(path, "adarnn.pt"))
        logger.info("Ensemble saved to %s", path)

    def load(self, path: str) -> None:
        """Load ensemble from a directory."""
        self._meta = LGBMModel()
        self._meta.load(os.path.join(path, "meta.pkl"))
        logger.info("Ensemble loaded from %s", path)

    def get_feature_importance(self) -> dict:
        """Return LightGBM base model feature importance (most interpretable)."""
        if self._lgbm is None:
            raise RuntimeError("Base LGBM not trained.")
        return self._lgbm.get_feature_importance()
