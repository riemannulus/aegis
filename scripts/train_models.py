#!/usr/bin/env python
"""Train all Aegis models (LightGBM, TRA, ADARNN, Ensemble).

Usage:
    python scripts/train_models.py [--symbol BTCUSDT] [--interval 30m]
                                   [--train-days 90] [--val-days 7]
                                   [--save-dir models/saved]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Ensure project root is on the path when run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("train_models")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train Aegis AI models")
    p.add_argument("--symbol", default="BTCUSDT", help="Binance symbol (default: BTCUSDT)")
    p.add_argument("--interval", default=settings.TIMEFRAME, help="Candle interval (default: 30m)")
    p.add_argument("--train-days", type=int, default=90, help="Training window in days")
    p.add_argument("--val-days", type=int, default=7, help="Validation window in days")
    p.add_argument("--save-dir", default="models/saved", help="Directory to save trained models")
    p.add_argument("--retrain", action="store_true", help="Rolling retrain mode")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    logger.info("%s Starting model training", settings.log_tag)
    logger.info(
        "Symbol=%s  Interval=%s  TrainDays=%d  ValDays=%d  SaveDir=%s",
        args.symbol, args.interval, args.train_days, args.val_days, args.save_dir,
    )

    save_dir = Path(args.save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 1. Load data
    # ------------------------------------------------------------------
    logger.info("Loading candle data from storage …")
    from data.storage import Storage
    from data.feature_engineer import FeatureEngineer

    storage = Storage()
    candles = storage.get_candles(
        symbol=args.symbol,
        interval=args.interval,
        limit=int(args.train_days * 48 + args.val_days * 48 + 200),  # extra buffer
    )
    if candles is None or len(candles) == 0:
        logger.error(
            "No candle data found. Run scripts/download_binance_vision.py first."
        )
        sys.exit(1)

    logger.info("Loaded %d candles", len(candles))

    # ------------------------------------------------------------------
    # 2. Feature engineering
    # ------------------------------------------------------------------
    logger.info("Computing features …")
    fe = FeatureEngineer()
    features_df = fe.compute(candles)
    logger.info("Feature matrix shape: %s", features_df.shape)

    # ------------------------------------------------------------------
    # 3. Train / split
    # ------------------------------------------------------------------
    from models.trainer import ModelTrainer

    trainer = ModelTrainer(save_dir=str(save_dir))

    if args.retrain:
        logger.info("Rolling retrain mode — retraining with latest window")
        trainer.retrain_rolling(
            features_df=features_df,
            train_days=args.train_days,
            val_days=args.val_days,
        )
    else:
        logger.info("Full training mode — training all models")
        trainer.train_all_models(
            features_df=features_df,
            train_days=args.train_days,
            val_days=args.val_days,
        )

    # ------------------------------------------------------------------
    # 4. Evaluate
    # ------------------------------------------------------------------
    logger.info("Evaluating models …")
    metrics = trainer.evaluate(features_df=features_df, val_days=args.val_days)
    for model_name, m in metrics.items():
        logger.info(
            "  %s — IC=%.4f  RankIC=%.4f  DirAcc=%.2f%%  Sharpe=%.3f",
            model_name,
            m.get("ic", float("nan")),
            m.get("rank_ic", float("nan")),
            m.get("direction_accuracy", float("nan")) * 100,
            m.get("sharpe", float("nan")),
        )

    logger.info("%s Model training complete. Models saved to %s", settings.log_tag, save_dir)


if __name__ == "__main__":
    main()
