"""Abstract base class for all Aegis prediction models."""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class BaseModel(ABC):
    """Interface that all Aegis models must implement."""

    @abstractmethod
    def train(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
    ) -> None:
        """Train the model on the provided data splits."""
        ...

    @abstractmethod
    def predict(self, X: np.ndarray) -> np.ndarray:
        """Return continuous return predictions for input features X."""
        ...

    @abstractmethod
    def save(self, path: str) -> None:
        """Persist the model to disk at the given path."""
        ...

    @abstractmethod
    def load(self, path: str) -> None:
        """Load a previously saved model from disk."""
        ...

    def get_feature_importance(self) -> dict:
        """Return feature importances as {feature_name: importance_score}.

        Optional — models that do not support this raise NotImplementedError.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support feature importance."
        )
