"""Tests for models/ — LightGBM, TRA, ADARNN, Ensemble, Trainer interfaces."""

from __future__ import annotations

import sys
import types

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Mock heavy optional dependencies so tests run without GPU/qlib installed
# ---------------------------------------------------------------------------
for _mod in ["lightgbm", "torch", "qlib"]:
    if _mod not in sys.modules:
        sys.modules[_mod] = types.ModuleType(_mod)

# Minimal lightgbm mock
_lgb = sys.modules["lightgbm"]
if not hasattr(_lgb, "LGBMRegressor"):
    class _LGBMRegressor:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.feature_importances_ = np.ones(1)
        def fit(self, X, y, eval_set=None, callbacks=None):
            self.feature_importances_ = np.ones(X.shape[1])
        def predict(self, X): return np.zeros(len(X))
    _lgb.LGBMRegressor = _LGBMRegressor
    _lgb.early_stopping = lambda n, **kw: None
    _lgb.log_evaluation = lambda *a, **kw: None

# Minimal torch mock
_torch = sys.modules["torch"]
if not hasattr(_torch, "nn"):
    _nn = types.ModuleType("torch.nn")

    class _TensorResult:
        """Minimal tensor-like for mock torch operations."""
        def __init__(self, data=1):
            if isinstance(data, np.ndarray):
                self._data = data
            elif isinstance(data, np.floating):  # numpy scalar → treat as scalar value
                self._data = np.array(float(data))
            elif isinstance(data, (int, float)):  # Python int/float → n-element zeros
                self._data = np.zeros(int(data))
            else:
                self._data = np.zeros(1)
        def to(self, *a, **kw): return self
        def backward(self): pass
        def item(self): return float(self._data.flat[0]) if self._data.size > 0 else 0.0
        def cpu(self): return self
        def numpy(self): return self._data
        def clone(self): return _TensorResult(self._data.copy())
        def detach(self): return self
        def size(self, dim=None):
            return self._data.shape[dim] if dim is not None else self._data.shape
        @property
        def shape(self): return self._data.shape
        def __len__(self): return len(self._data)
        def __iter__(self):
            yield self                    # pred (used by ADARNN: preds, hiddens = result)
            yield _TensorResult(0)        # hidden (size=0 → _segment_mmd returns early)
        def __getitem__(self, key):
            if isinstance(key, int):
                return _TensorResult(self._data)  # int[0] returns self (ADARNN [0] pattern)
            return _TensorResult(self._data[key])
        def __add__(self, o):
            return _TensorResult(self._data + (o._data if isinstance(o, _TensorResult) else o))
        def __radd__(self, o):
            return _TensorResult((o._data if isinstance(o, _TensorResult) else o) + self._data)
        def __mul__(self, o):
            return _TensorResult(self._data * (o._data if isinstance(o, _TensorResult) else o))
        def __rmul__(self, o):
            return _TensorResult((o._data if isinstance(o, _TensorResult) else o) * self._data)
        def __truediv__(self, o):
            denom = (o._data if isinstance(o, _TensorResult) else o)
            return _TensorResult(self._data / (denom if np.any(denom != 0) else 1))
        def sum(self, *a, **kw): return _TensorResult(np.array(np.sum(self._data)))
        def mean(self, *a, **kw): return _TensorResult(np.array(np.mean(self._data)))

    class _Module:
        def __init__(self): pass
        def parameters(self): return iter([])
        def train(self, *a, **kw): pass
        def eval(self): pass
        def to(self, *a, **kw): return self
        def state_dict(self): return {}
        def load_state_dict(self, d): pass
        def __call__(self, *a, **kw):
            if a:
                x = a[0]
                if isinstance(x, _TensorResult):
                    n = x._data.shape[0] if x._data.ndim > 0 else 1
                    return _TensorResult(n)
                elif hasattr(x, 'shape') and len(x.shape) > 0:
                    return _TensorResult(x.shape[0])
            return _TensorResult(1)

    _nn.Module = _Module
    _nn.Linear = type("Linear", (_Module,), {"__init__": lambda s, *a, **k: None})
    _nn.LSTM = type("LSTM", (_Module,), {"__init__": lambda s, *a, **k: None})
    _nn.GRU = type("GRU", (_Module,), {"__init__": lambda s, *a, **k: None})
    _nn.Softmax = type("Softmax", (_Module,), {"__init__": lambda s, **k: None})
    _nn.Sequential = type("Sequential", (_Module,), {"__init__": lambda s, *a: None})
    _nn.ReLU = type("ReLU", (_Module,), {"__init__": lambda s, **k: None})
    _nn.ModuleList = type("ModuleList", (_Module,), {"__init__": lambda s, lst=None: None, "__iter__": lambda s: iter([])})
    _nn.MSELoss = type("MSELoss", (_Module,), {"__init__": lambda s, **k: None})
    _torch.nn = _nn
    sys.modules["torch.nn"] = _nn
    _torch.device = lambda x: x
    _torch.from_numpy = lambda x: _TensorResult(x)
    _torch.tensor = lambda x, **kw: _TensorResult(np.array(x) if not isinstance(x, np.ndarray) else x)
    _torch.zeros = lambda *a, **kw: _TensorResult(np.zeros(a))
    _torch.FloatTensor = np.array
    _torch.save = lambda obj, path, **kw: None
    _torch.load = lambda path, **kw: {}
    _torch.no_grad = lambda: type("ctx", (), {"__enter__": lambda s: s, "__exit__": lambda s, *a: None})()
    _torch.optim = types.ModuleType("torch.optim")
    _torch.optim.Adam = lambda params, **kw: type("opt", (), {
        "zero_grad": lambda s: None,
        "step": lambda s: None,
    })()
    sys.modules["torch.optim"] = _torch.optim


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

N_SAMPLES = 200
N_FEATURES = 30
LOOKBACK = 10


def _make_xy(n=N_SAMPLES, f=N_FEATURES):
    rng = np.random.default_rng(42)
    X = rng.standard_normal((n, f)).astype(np.float32)
    y = rng.standard_normal(n).astype(np.float32)
    split = int(n * 0.8)
    return X[:split], y[:split], X[split:], y[split:]


# ---------------------------------------------------------------------------
# BaseModel interface
# ---------------------------------------------------------------------------

class TestBaseModelInterface:
    def test_base_model_is_abstract(self):
        from models.base import BaseModel
        with pytest.raises(TypeError):
            BaseModel()  # cannot instantiate abstract class

    def test_base_model_has_required_methods(self):
        import inspect
        from models.base import BaseModel
        abstract_methods = {
            name for name, member in inspect.getmembers(BaseModel)
            if getattr(member, "__isabstractmethod__", False)
        }
        assert "train" in abstract_methods
        assert "predict" in abstract_methods
        assert "save" in abstract_methods
        assert "load" in abstract_methods


# ---------------------------------------------------------------------------
# LightGBM model
# ---------------------------------------------------------------------------

class TestLGBMModel:
    def test_lgbm_is_base_model(self):
        from models.base import BaseModel
        from models.lgbm_model import LGBMModel
        assert issubclass(LGBMModel, BaseModel)

    def test_lgbm_train_predict(self, tmp_path):
        from models.lgbm_model import LGBMModel
        X_tr, y_tr, X_val, y_val = _make_xy()
        model = LGBMModel()
        model.train(X_tr, y_tr, X_val, y_val)
        preds = model.predict(X_val)
        assert preds.shape == (len(X_val),)

    def test_lgbm_save_load(self, tmp_path):
        from models.lgbm_model import LGBMModel
        X_tr, y_tr, X_val, y_val = _make_xy()
        model = LGBMModel()
        model.train(X_tr, y_tr, X_val, y_val)
        path = str(tmp_path / "lgbm.pkl")
        model.save(path)
        model2 = LGBMModel()
        model2.load(path)
        preds = model2.predict(X_val)
        assert preds.shape == (len(X_val),)

    def test_lgbm_feature_importance(self):
        from models.lgbm_model import LGBMModel
        X_tr, y_tr, X_val, y_val = _make_xy()
        model = LGBMModel()
        model.train(X_tr, y_tr, X_val, y_val)
        importance = model.get_feature_importance()
        assert isinstance(importance, dict)
        assert len(importance) > 0


# ---------------------------------------------------------------------------
# TRA model
# ---------------------------------------------------------------------------

class TestTRAModel:
    def test_tra_is_base_model(self):
        from models.base import BaseModel
        from models.tra_model import TRAModel
        assert issubclass(TRAModel, BaseModel)

    def test_tra_train_predict(self):
        from models.tra_model import TRAModel
        X_tr, y_tr, X_val, y_val = _make_xy()
        model = TRAModel(input_size=N_FEATURES, lookback=LOOKBACK)
        model.train(X_tr, y_tr, X_val, y_val)
        preds = model.predict(X_val)
        assert len(preds) == len(X_val)

    def test_tra_router_weights_accessible(self):
        from models.tra_model import TRAModel
        X_tr, y_tr, X_val, y_val = _make_xy()
        model = TRAModel(input_size=N_FEATURES, lookback=LOOKBACK)
        model.train(X_tr, y_tr, X_val, y_val)
        weights = model.get_router_weights(X_val[:1])
        assert weights is not None
        assert len(weights) > 0


# ---------------------------------------------------------------------------
# ADARNN model
# ---------------------------------------------------------------------------

class TestADARNNModel:
    def test_adarnn_is_base_model(self):
        from models.base import BaseModel
        from models.adarnn_model import ADANNModel
        assert issubclass(ADANNModel, BaseModel)

    def test_adarnn_train_predict(self):
        from models.adarnn_model import ADANNModel
        X_tr, y_tr, X_val, y_val = _make_xy()
        model = ADANNModel(input_size=N_FEATURES)
        model.train(X_tr, y_tr, X_val, y_val)
        preds = model.predict(X_val)
        assert len(preds) == len(X_val)


# ---------------------------------------------------------------------------
# Ensemble model
# ---------------------------------------------------------------------------

class TestEnsembleModel:
    def test_ensemble_is_base_model(self):
        from models.base import BaseModel
        from models.ensemble import EnsembleModel
        assert issubclass(EnsembleModel, BaseModel)

    def test_ensemble_predict_shape(self):
        from models.ensemble import EnsembleModel
        X_tr, y_tr, X_val, y_val = _make_xy()
        # Provide mock sub-model predictions
        lgbm_preds = np.random.randn(len(X_val))
        tra_preds  = np.random.randn(len(X_val))
        ada_preds  = np.random.randn(len(X_val))

        model = EnsembleModel()
        # Train with stacked predictions
        meta_X_train = np.column_stack([
            np.random.randn(len(X_tr)),
            np.random.randn(len(X_tr)),
            np.random.randn(len(X_tr)),
        ])
        model.train(meta_X_train, y_tr, np.column_stack([lgbm_preds, tra_preds, ada_preds]), y_val)
        meta_X_val = np.column_stack([lgbm_preds, tra_preds, ada_preds])
        preds = model.predict(meta_X_val)
        assert preds.shape == (len(X_val),)
