"""LightGBM model for Aegis trading system."""

from __future__ import annotations

import logging
import os
from typing import Optional

import lightgbm as lgb
import numpy as np
from scipy.stats import spearmanr

from models.base import BaseModel

logger = logging.getLogger(__name__)


class LGBMModel(BaseModel):
    """LightGBM regression model predicting continuous return values."""

    def __init__(
        self,
        num_leaves: int = 31,
        learning_rate: float = 0.05,
        n_estimators: int = 500,
        min_child_samples: int = 20,
        subsample: float = 0.8,
        colsample_bytree: float = 0.8,
        reg_alpha: float = 0.1,
        reg_lambda: float = 0.1,
        early_stopping_rounds: int = 50,
        feature_names: Optional[list[str]] = None,
    ) -> None:
        self.params = {
            "num_leaves": num_leaves,
            "learning_rate": learning_rate,
            "n_estimators": n_estimators,
            "min_child_samples": min_child_samples,
            "subsample": subsample,
            "colsample_bytree": colsample_bytree,
            "reg_alpha": reg_alpha,
            "reg_lambda": reg_lambda,
            "objective": "regression",
            "verbose": -1,
            "n_jobs": -1,
        }
        self.early_stopping_rounds = early_stopping_rounds
        self.feature_names = feature_names
        self._model: Optional[lgb.Booster] = None

    def train(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
    ) -> None:
        """Train with early stopping on validation loss, log IC at each 50 rounds."""
        feature_names = self.feature_names or [f"f{i}" for i in range(X_train.shape[1])]

        dtrain = lgb.Dataset(X_train, label=y_train, feature_name=feature_names)
        dval = lgb.Dataset(X_val, label=y_val, reference=dtrain, feature_name=feature_names)

        callbacks = [
            lgb.early_stopping(self.early_stopping_rounds, verbose=False),
            lgb.log_evaluation(period=50),
        ]

        params = dict(self.params)
        n_estimators = params.pop("n_estimators")

        self._model = lgb.train(
            params,
            dtrain,
            num_boost_round=n_estimators,
            valid_sets=[dval],
            callbacks=callbacks,
        )

        val_preds = self._model.predict(X_val)
        ic = float(np.corrcoef(val_preds, y_val)[0, 1])
        rank_ic, _ = spearmanr(val_preds, y_val)
        logger.info(
            "LightGBM training complete | best_iteration=%d | IC=%.4f | Rank_IC=%.4f",
            self._model.best_iteration,
            ic,
            rank_ic,
        )

    def predict(self, X: np.ndarray) -> np.ndarray:
        if self._model is None:
            raise RuntimeError("Model not trained. Call train() or load() first.")
        return self._model.predict(X)

    def save(self, path: str) -> None:
        if self._model is None:
            raise RuntimeError("No model to save.")
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        self._model.save_model(path)
        logger.info("LightGBM model saved to %s", path)

    def load(self, path: str) -> None:
        self._model = lgb.Booster(model_file=path)
        logger.info("LightGBM model loaded from %s", path)

    def get_feature_importance(self) -> dict:
        if self._model is None:
            raise RuntimeError("Model not trained.")
        names = self._model.feature_name()
        scores = self._model.feature_importance(importance_type="gain")
        total = scores.sum() or 1.0
        return {name: float(score / total) for name, score in zip(names, scores)}
