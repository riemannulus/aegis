"""Temporal Routing Adaptor (TRA) model for Aegis trading system.

Implements a Router Network that routes the current market state to one of K
independent LSTM/GRU-based predictor networks.  The final prediction is the
weighted sum of all predictors' outputs, where the weights come from the router.
Router weights are exposed so regime_detector.py can read the active predictor.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import numpy as np
import torch
import torch.nn as nn
from scipy.stats import spearmanr

from models.base import BaseModel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Neural network components
# ---------------------------------------------------------------------------

class _RouterNetwork(nn.Module):
    """Lightweight MLP that outputs soft weights over K predictors."""

    def __init__(self, input_size: int, hidden_size: int, num_predictors: int) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_size, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, num_predictors),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (batch, input_size) → weights: (batch, K) after softmax."""
        return torch.softmax(self.net(x), dim=-1)


class _Predictor(nn.Module):
    """Single GRU-based predictor."""

    def __init__(self, input_size: int, hidden_size: int) -> None:
        super().__init__()
        self.gru = nn.GRU(input_size, hidden_size, batch_first=True)
        self.fc = nn.Linear(hidden_size, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (batch, seq_len, input_size) → (batch,)"""
        _, h = self.gru(x)          # h: (1, batch, hidden)
        return self.fc(h.squeeze(0)).squeeze(-1)  # (batch,)


class _TRANet(nn.Module):
    """Full TRA network: router + K predictors."""

    def __init__(
        self,
        input_size: int,
        hidden_size: int,
        num_predictors: int,
        router_hidden: int,
    ) -> None:
        super().__init__()
        self.router = _RouterNetwork(input_size, router_hidden, num_predictors)
        self.predictors = nn.ModuleList(
            [_Predictor(input_size, hidden_size) for _ in range(num_predictors)]
        )
        # Cache last router weights for external inspection
        self._last_weights: Optional[torch.Tensor] = None

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (batch, seq_len, input_size) → predictions: (batch,)"""
        # Use the last time-step features as router input
        router_input = x[:, -1, :]                         # (batch, input_size)
        weights = self.router(router_input)                 # (batch, K)
        self._last_weights = weights.detach()

        pred_stack = torch.stack(
            [p(x) for p in self.predictors], dim=1
        )                                                   # (batch, K)
        return (weights * pred_stack).sum(dim=1)            # (batch,)

    @property
    def last_router_weights(self) -> Optional[np.ndarray]:
        if self._last_weights is None:
            return None
        return self._last_weights.cpu().numpy()


# ---------------------------------------------------------------------------
# BaseModel wrapper
# ---------------------------------------------------------------------------

class TRAModel(BaseModel):
    """Temporal Routing Adaptor regression model.

    Parameters
    ----------
    num_predictors : int
        Number of independent predictors K (typically 3-5).
    hidden_size : int
        Hidden size of each GRU predictor.
    router_hidden : int
        Hidden size of the router MLP.
    lookback_window : int
        Sequence length fed into each predictor (48 = 24 h on 30 m bars).
    learning_rate : float
        Adam learning rate.
    num_epochs : int
        Training epochs.
    batch_size : int
        Mini-batch size.
    device : str
        "cpu" or "cuda".
    """

    def __init__(
        self,
        num_predictors: int = 4,
        hidden_size: int = 64,
        router_hidden: int = 32,
        lookback_window: int = 48,
        learning_rate: float = 1e-3,
        num_epochs: int = 50,
        batch_size: int = 256,
        device: str = "cpu",
        input_size: Optional[int] = None,
        lookback: Optional[int] = None,
    ) -> None:
        if lookback is not None:
            lookback_window = lookback
        self.num_predictors = num_predictors
        self.hidden_size = hidden_size
        self.router_hidden = router_hidden
        self.lookback_window = lookback_window
        self.learning_rate = learning_rate
        self.num_epochs = num_epochs
        self.batch_size = batch_size
        self.device = torch.device(device)
        self._net: Optional[_TRANet] = None
        self._input_size: int = 0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_sequences(self, X: np.ndarray) -> np.ndarray:
        """Convert flat feature matrix → (N, lookback, features) sequences."""
        n, f = X.shape
        out = []
        for i in range(self.lookback_window, n + 1):
            out.append(X[i - self.lookback_window: i])
        return np.array(out, dtype=np.float32)      # (N-lb, lb, f)

    def _to_tensor(self, arr: np.ndarray) -> torch.Tensor:
        return torch.from_numpy(arr).to(self.device)

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
        lb = self.lookback_window
        self._input_size = X_train.shape[1]

        X_seq = self._make_sequences(X_train)       # (N-lb, lb, f)
        y_seq = y_train[lb - 1:].astype(np.float32)  # align labels

        X_val_seq = self._make_sequences(X_val)
        y_val_seq = y_val[lb - 1:].astype(np.float32)

        self._net = _TRANet(
            input_size=self._input_size,
            hidden_size=self.hidden_size,
            num_predictors=self.num_predictors,
            router_hidden=self.router_hidden,
        ).to(self.device)

        optimizer = torch.optim.Adam(self._net.parameters(), lr=self.learning_rate)
        criterion = nn.MSELoss()

        n = len(X_seq)
        best_val_loss = float("inf")
        best_state = None

        for epoch in range(self.num_epochs):
            self._net.train()
            idx = np.random.permutation(n)
            epoch_loss = 0.0
            batches = 0
            for start in range(0, n, self.batch_size):
                batch_idx = idx[start: start + self.batch_size]
                xb = self._to_tensor(X_seq[batch_idx])
                yb = self._to_tensor(y_seq[batch_idx])

                optimizer.zero_grad()
                preds = self._net(xb)
                loss = criterion(preds, yb)
                loss.backward()
                optimizer.step()
                epoch_loss += loss.item()
                batches += 1

            # Validation
            self._net.eval()
            with torch.no_grad():
                xv = self._to_tensor(X_val_seq)
                yv = self._to_tensor(y_val_seq)
                val_preds = self._net(xv)
                val_loss = criterion(val_preds, yv).item()

            if val_loss < best_val_loss:
                best_val_loss = val_loss
                best_state = {k: v.clone() for k, v in self._net.state_dict().items()}

            if (epoch + 1) % 10 == 0:
                logger.info(
                    "TRA epoch %d/%d | train_loss=%.6f | val_loss=%.6f",
                    epoch + 1, self.num_epochs,
                    epoch_loss / max(batches, 1),
                    val_loss,
                )

        # Restore best checkpoint
        if best_state is not None:
            self._net.load_state_dict(best_state)

        # Final IC on validation set
        self._net.eval()
        with torch.no_grad():
            val_preds_np = self._net(self._to_tensor(X_val_seq)).cpu().numpy()
        ic = float(np.corrcoef(val_preds_np, y_val_seq)[0, 1])
        rank_ic, _ = spearmanr(val_preds_np, y_val_seq)
        logger.info(
            "TRA training complete | val_IC=%.4f | val_Rank_IC=%.4f | best_val_loss=%.6f",
            ic, rank_ic, best_val_loss,
        )

    def predict(self, X: np.ndarray) -> np.ndarray:
        if self._net is None:
            raise RuntimeError("Model not trained. Call train() or load() first.")
        X_seq = self._make_sequences(X)
        self._net.eval()
        with torch.no_grad():
            preds = self._net(self._to_tensor(X_seq)).cpu().numpy()
        # Pad the first (lookback_window - 1) rows with NaN for length alignment
        pad = np.full(self.lookback_window - 1, np.nan, dtype=np.float32)
        return np.concatenate([pad, preds])

    def save(self, path: str) -> None:
        if self._net is None:
            raise RuntimeError("No model to save.")
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        torch.save(
            {
                "state_dict": self._net.state_dict(),
                "input_size": self._input_size,
                "num_predictors": self.num_predictors,
                "hidden_size": self.hidden_size,
                "router_hidden": self.router_hidden,
                "lookback_window": self.lookback_window,
            },
            path,
        )
        logger.info("TRA model saved to %s", path)

    def load(self, path: str) -> None:
        checkpoint = torch.load(path, map_location=self.device)
        self._input_size = checkpoint["input_size"]
        self.num_predictors = checkpoint["num_predictors"]
        self.hidden_size = checkpoint["hidden_size"]
        self.router_hidden = checkpoint["router_hidden"]
        self.lookback_window = checkpoint["lookback_window"]
        self._net = _TRANet(
            input_size=self._input_size,
            hidden_size=self.hidden_size,
            num_predictors=self.num_predictors,
            router_hidden=self.router_hidden,
        ).to(self.device)
        self._net.load_state_dict(checkpoint["state_dict"])
        self._net.eval()
        logger.info("TRA model loaded from %s", path)

    # ------------------------------------------------------------------
    # TRA-specific: expose router weights for regime detection
    # ------------------------------------------------------------------

    def get_router_weights(self, X: np.ndarray) -> np.ndarray:
        """Return router weights for the last sample in X.

        Shape: (num_predictors,) — the probability each predictor is active.
        """
        if self._net is None:
            raise RuntimeError("Model not trained.")
        X_seq = self._make_sequences(X)
        self._net.eval()
        with torch.no_grad():
            _ = self._net(self._to_tensor(X_seq[-1:]))
        weights = self._net.last_router_weights
        return weights[0] if weights is not None else np.ones(self.num_predictors) / self.num_predictors
