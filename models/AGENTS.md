<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-20 | Updated: 2026-03-20 -->

# models

## Purpose
Machine learning prediction models for crypto futures price forecasting. Implements a stacking ensemble of three model types (LightGBM, TRA, AdaRNN) with a meta-model, plus a training/retraining pipeline.

## Key Files

| File | Description |
|------|-------------|
| `base.py` | `BaseModel` ABC — interface all models implement: `train()`, `predict()`, `save()`, `load()`, `get_feature_importance()` |
| `lgbm_model.py` | `LGBMModel` — LightGBM gradient boosting model |
| `tra_model.py` | `TRAModel` — Temporal Relational Attention model (PyTorch) |
| `adarnn_model.py` | `AdaRNNModel` — Adaptive RNN model (PyTorch) |
| `ensemble.py` | `EnsembleModel` — Stacking ensemble using 5-fold time-based CV. OOF predictions from the 3 base models feed a meta LightGBM |
| `trainer.py` | `ModelTrainer` — Training pipeline with `train_all_models()` and `retrain_rolling()` (7-day rolling window retraining). Evaluates via IC, Rank IC, direction accuracy, Sharpe |

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `saved/` | Persisted model artifacts (`.lgbm`, `.pkl` files) |

## For AI Agents

### Working In This Directory
- All models inherit from `BaseModel` and implement `train()`, `predict()`, `save()`, `load()`
- `predict()` returns continuous return predictions (not classification)
- Ensemble uses time-based 5-fold CV to avoid look-ahead bias
- Training is CPU-only (no GPU required) — PyTorch models run on CPU
- Rolling retraining: 90-day window, retrained every 7 days (configurable)
- Validation split: last 10% of training window

### Testing Requirements
- `test_models.py` in tests/
- Use small synthetic data for unit tests (avoid loading real data)
- Verify predictions have correct shape and are finite

### Common Patterns
- `model.predict(X)` where X is `np.ndarray` of shape `(n_samples, n_features)`
- `ensemble.load("models/saved/ensemble.pkl")` to restore trained model
- Evaluation metrics: IC (Information Coefficient), Rank IC (Spearman), Direction Accuracy

## Dependencies

### Internal
- `data/storage.py` — Trainer pulls training data from Storage
- `data/feature_engineer.py` — Features feed into model training

### External
- `lightgbm` — Gradient boosting (LGBMModel + meta-model)
- `torch` — PyTorch for TRA and AdaRNN
- `scipy` — Spearman correlation for evaluation
- `numpy`, `scikit-learn` — Data processing

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
