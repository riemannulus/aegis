"""ADARNN (Adaptive RNN) model for Aegis trading system.

Splits the time series into N segments and minimises cross-segment distribution
divergence with an adversarial MMD loss, forcing the GRU backbone to learn
distribution-invariant features across market regimes.
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
# Helpers
# ---------------------------------------------------------------------------

def _mmd_loss(x: torch.Tensor, y: torch.Tensor, sigma: float = 1.0) -> torch.Tensor:
    """Unbiased MMD^2 with Gaussian kernel between two batches of embeddings."""
    def _kernel(a: torch.Tensor, b: torch.Tensor) -> torch.Tensor:
        diff = a.unsqueeze(1) - b.unsqueeze(0)          # (n, m, d)
        sq_dist = (diff ** 2).sum(-1)                    # (n, m)
        return torch.exp(-sq_dist / (2 * sigma ** 2))

    kxx = _kernel(x, x)
    kyy = _kernel(y, y)
    kxy = _kernel(x, y)
    n, m = x.size(0), y.size(0)
    # Remove diagonal for unbiased estimate
    eye_x = torch.eye(n, device=x.device)
    eye_y = torch.eye(m, device=y.device)
    kxx = (kxx - eye_x).sum() / max(n * (n - 1), 1)
    kyy = (kyy - eye_y).sum() / max(m * (m - 1), 1)
    kxy = kxy.mean()
    return kxx + kyy - 2 * kxy


# ---------------------------------------------------------------------------
# Neural network
# ---------------------------------------------------------------------------

class _AdaRNNNet(nn.Module):
    """GRU backbone with per-segment distribution alignment."""

    def __init__(self, input_size: int, hidden_size: int, num_layers: int = 1) -> None:
        super().__init__()
        self.gru = nn.GRU(input_size, hidden_size, num_layers=num_layers, batch_first=True)
        self.fc = nn.Linear(hidden_size, 1)

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """x: (batch, seq_len, features) → (pred: batch, hidden: batch, hidden_size)"""
        out, h = self.gru(x)
        last_hidden = h[-1]                             # (batch, hidden)
        pred = self.fc(last_hidden).squeeze(-1)         # (batch,)
        return pred, last_hidden


# ---------------------------------------------------------------------------
# BaseModel wrapper
# ---------------------------------------------------------------------------

class AdaRNNModel(BaseModel):
    """ADARNN regression model.

    Parameters
    ----------
    num_segments : int
        Number of time segments to split training data into for MMD alignment.
    hidden_size : int
        GRU hidden dimension.
    lookback_window : int
        Sequence length per sample.
    learning_rate : float
    num_epochs : int
    batch_size : int
    mmd_weight : float
        Coefficient of the MMD adversarial loss term.
    device : str
    """

    def __init__(
        self,
        num_segments: int = 5,
        hidden_size: int = 64,
        lookback_window: int = 48,
        learning_rate: float = 1e-3,
        num_epochs: int = 50,
        batch_size: int = 256,
        mmd_weight: float = 0.1,
        device: str = "cpu",
    ) -> None:
        self.num_segments = num_segments
        self.hidden_size = hidden_size
        self.lookback_window = lookback_window
        self.learning_rate = learning_rate
        self.num_epochs = num_epochs
        self.batch_size = batch_size
        self.mmd_weight = mmd_weight
        self.device = torch.device(device)
        self._net: Optional[_AdaRNNNet] = None
        self._input_size: int = 0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_sequences(self, X: np.ndarray) -> np.ndarray:
        n, f = X.shape
        seqs = []
        for i in range(self.lookback_window, n + 1):
            seqs.append(X[i - self.lookback_window: i])
        return np.array(seqs, dtype=np.float32)

    def _to_tensor(self, arr: np.ndarray) -> torch.Tensor:
        return torch.from_numpy(arr).to(self.device)

    def _segment_mmd(self, hiddens: torch.Tensor) -> torch.Tensor:
        """Compute average pairwise MMD across num_segments chunks of the batch."""
        n = hiddens.size(0)
        seg_size = max(n // self.num_segments, 1)
        segments = [
            hiddens[i * seg_size: (i + 1) * seg_size]
            for i in range(self.num_segments)
            if i * seg_size < n
        ]
        if len(segments) < 2:
            return torch.tensor(0.0, device=self.device)
        total = torch.tensor(0.0, device=self.device)
        pairs = 0
        for i in range(len(segments)):
            for j in range(i + 1, len(segments)):
                if segments[i].size(0) > 0 and segments[j].size(0) > 0:
                    total += _mmd_loss(segments[i], segments[j])
                    pairs += 1
        return total / max(pairs, 1)

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

        X_seq = self._make_sequences(X_train)
        y_seq = y_train[lb - 1:].astype(np.float32)

        X_val_seq = self._make_sequences(X_val)
        y_val_seq = y_val[lb - 1:].astype(np.float32)

        self._net = _AdaRNNNet(self._input_size, self.hidden_size).to(self.device)
        optimizer = torch.optim.Adam(self._net.parameters(), lr=self.learning_rate)
        criterion = nn.MSELoss()

        n = len(X_seq)
        best_val_loss = float("inf")
        best_state = None

        for epoch in range(self.num_epochs):
            self._net.train()
            idx = np.random.permutation(n)
            epoch_pred_loss = 0.0
            epoch_mmd_loss = 0.0
            batches = 0

            for start in range(0, n, self.batch_size):
                batch_idx = idx[start: start + self.batch_size]
                xb = self._to_tensor(X_seq[batch_idx])
                yb = self._to_tensor(y_seq[batch_idx])

                optimizer.zero_grad()
                preds, hiddens = self._net(xb)
                pred_loss = criterion(preds, yb)
                mmd = self._segment_mmd(hiddens)
                loss = pred_loss + self.mmd_weight * mmd
                loss.backward()
                optimizer.step()
                epoch_pred_loss += pred_loss.item()
                epoch_mmd_loss += mmd.item()
                batches += 1

            # Validation
            self._net.eval()
            with torch.no_grad():
                xv = self._to_tensor(X_val_seq)
                yv = self._to_tensor(y_val_seq)
                val_preds, _ = self._net(xv)
                val_loss = criterion(val_preds, yv).item()

            if val_loss < best_val_loss:
                best_val_loss = val_loss
                best_state = {k: v.clone() for k, v in self._net.state_dict().items()}

            if (epoch + 1) % 10 == 0:
                logger.info(
                    "ADARNN epoch %d/%d | pred_loss=%.6f | mmd=%.6f | val_loss=%.6f",
                    epoch + 1, self.num_epochs,
                    epoch_pred_loss / max(batches, 1),
                    epoch_mmd_loss / max(batches, 1),
                    val_loss,
                )

        if best_state is not None:
            self._net.load_state_dict(best_state)

        # Final IC
        self._net.eval()
        with torch.no_grad():
            val_preds_np = self._net(self._to_tensor(X_val_seq))[0].cpu().numpy()
        ic = float(np.corrcoef(val_preds_np, y_val_seq)[0, 1])
        rank_ic, _ = spearmanr(val_preds_np, y_val_seq)
        logger.info(
            "ADARNN training complete | val_IC=%.4f | val_Rank_IC=%.4f | best_val_loss=%.6f",
            ic, rank_ic, best_val_loss,
        )

    def predict(self, X: np.ndarray) -> np.ndarray:
        if self._net is None:
            raise RuntimeError("Model not trained. Call train() or load() first.")
        X_seq = self._make_sequences(X)
        self._net.eval()
        with torch.no_grad():
            preds = self._net(self._to_tensor(X_seq))[0].cpu().numpy()
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
                "hidden_size": self.hidden_size,
                "lookback_window": self.lookback_window,
                "num_segments": self.num_segments,
            },
            path,
        )
        logger.info("ADARNN model saved to %s", path)

    def load(self, path: str) -> None:
        checkpoint = torch.load(path, map_location=self.device)
        self._input_size = checkpoint["input_size"]
        self.hidden_size = checkpoint["hidden_size"]
        self.lookback_window = checkpoint["lookback_window"]
        self.num_segments = checkpoint["num_segments"]
        self._net = _AdaRNNNet(self._input_size, self.hidden_size).to(self.device)
        self._net.load_state_dict(checkpoint["state_dict"])
        self._net.eval()
        logger.info("ADARNN model loaded from %s", path)
