"""SQLAlchemy + SQLite storage layer for Aegis."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Column, Integer, Float, String, Boolean, Text, DateTime,
    create_engine, event, text
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


DB_PATH = os.environ.get("AEGIS_DB_PATH", "data/aegis.db")
ENGINE_URL = f"sqlite:///{DB_PATH}"


class Base(DeclarativeBase):
    pass


class Candle(Base):
    __tablename__ = "candles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(Integer, nullable=False, unique=True, index=True)  # ms epoch
    symbol = Column(String(32), nullable=False, default="BTCUSDT")
    interval = Column(String(8), nullable=False, default="30m")
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    quote_volume = Column(Float)
    count = Column(Integer)
    taker_buy_volume = Column(Float)
    taker_buy_quote_volume = Column(Float)


class FundingRate(Base):
    __tablename__ = "funding_rates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(Integer, nullable=False, index=True)
    symbol = Column(String(32), nullable=False)
    funding_rate = Column(Float, nullable=False)
    mark_price = Column(Float)


class Signal(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(Integer, nullable=False, index=True)
    model_name = Column(String(64), nullable=False)
    prediction = Column(Float, nullable=False)
    position_signal = Column(Float, nullable=False)


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(Integer, nullable=False, index=True)
    side = Column(String(8), nullable=False)
    price = Column(Float)
    amount = Column(Float, nullable=False)
    status = Column(String(32), nullable=False)
    order_id = Column(String(128))
    leverage = Column(Integer)


class Position(Base):
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(Integer, nullable=False, index=True)
    side = Column(String(8), nullable=False)
    entry_price = Column(Float, nullable=False)
    size = Column(Float, nullable=False)
    unrealized_pnl = Column(Float)
    liquidation_price = Column(Float)


class Decision(Base):
    __tablename__ = "decisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(Integer, nullable=False, index=True)
    candle_id = Column(Integer)
    decision = Column(String(16), nullable=False)   # BUY, SELL, HOLD, SKIP
    direction = Column(String(8))                    # long, short, flat
    z_score = Column(Float)
    regime = Column(String(16))
    reason = Column(Text)
    full_record = Column(Text)  # JSON blob


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(Integer, nullable=False, index=True)
    side = Column(String(8), nullable=False)
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=False)
    pnl = Column(Float, nullable=False)
    funding_cost = Column(Float, default=0.0)


def _enable_wal(dbapi_conn, _connection_record):
    dbapi_conn.execute("PRAGMA journal_mode=WAL")
    dbapi_conn.execute("PRAGMA synchronous=NORMAL")


class Storage:
    """Thread-safe SQLite storage with upsert support."""

    def __init__(self, db_path: str = DB_PATH):
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
        self.engine = create_engine(f"sqlite:///{db_path}", echo=False)
        event.listen(self.engine, "connect", _enable_wal)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)

    def _session(self) -> Session:
        return self.SessionLocal()

    def init_db(self) -> None:
        """Ensure all tables exist. Safe to call multiple times."""
        Base.metadata.create_all(self.engine)

    # ------------------------------------------------------------------
    # Candles
    # ------------------------------------------------------------------

    def upsert_candles(self, rows: list[dict]) -> int:
        """Insert or update candle rows. Returns number of rows upserted."""
        if not rows:
            return 0
        with self._session() as sess:
            count = 0
            for row in rows:
                existing = sess.query(Candle).filter_by(timestamp=row["timestamp"]).first()
                if existing:
                    for k, v in row.items():
                        setattr(existing, k, v)
                else:
                    sess.add(Candle(**row))
                    count += 1
            sess.commit()
        return count

    def get_candles(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "30m",
        start_ts: int | None = None,
        end_ts: int | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        with self._session() as sess:
            q = sess.query(Candle).filter_by(symbol=symbol, interval=interval)
            if start_ts:
                q = q.filter(Candle.timestamp >= start_ts)
            if end_ts:
                q = q.filter(Candle.timestamp <= end_ts)
            q = q.order_by(Candle.timestamp.asc())
            if limit:
                q = q.limit(limit)
            return [row.__dict__ for row in q.all()]

    def get_recent_candles(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "30m",
        limit: int = 200,
    ):
        """Return recent candles as a DataFrame (sorted ascending by timestamp)."""
        import pandas as pd

        rows = self.get_candles(symbol=symbol, interval=interval, limit=limit)
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        df.drop(columns=["_sa_instance_state"], errors="ignore", inplace=True)
        return df.sort_values("timestamp").reset_index(drop=True)

    def get_latest_candle_timestamp(self, symbol: str = "BTCUSDT", interval: str = "30m") -> int | None:
        with self._session() as sess:
            row = (
                sess.query(Candle)
                .filter_by(symbol=symbol, interval=interval)
                .order_by(Candle.timestamp.desc())
                .first()
            )
            return row.timestamp if row else None

    # ------------------------------------------------------------------
    # Funding rates
    # ------------------------------------------------------------------

    def upsert_funding_rate(self, row: dict) -> None:
        with self._session() as sess:
            existing = sess.query(FundingRate).filter_by(
                timestamp=row["timestamp"], symbol=row["symbol"]
            ).first()
            if existing:
                for k, v in row.items():
                    setattr(existing, k, v)
            else:
                sess.add(FundingRate(**row))
            sess.commit()

    def get_recent_funding_rates(
        self,
        symbol: str = "BTCUSDT",
        limit: int = 100,
    ):
        """Return recent funding rates as a DataFrame (sorted ascending by timestamp)."""
        import pandas as pd

        rows = self.get_funding_rates(symbol=symbol, limit=limit)
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        df.drop(columns=["_sa_instance_state"], errors="ignore", inplace=True)
        return df.sort_values("timestamp").reset_index(drop=True)

    def get_funding_rates(self, symbol: str, limit: int = 100) -> list[dict]:
        with self._session() as sess:
            rows = (
                sess.query(FundingRate)
                .filter_by(symbol=symbol)
                .order_by(FundingRate.timestamp.desc())
                .limit(limit)
                .all()
            )
            return [r.__dict__ for r in reversed(rows)]

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    def insert_signal(self, row: dict) -> None:
        with self._session() as sess:
            sess.add(Signal(**row))
            sess.commit()

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    def insert_order(self, row: dict) -> None:
        with self._session() as sess:
            sess.add(Order(**row))
            sess.commit()

    def save_order(self, row: dict) -> None:
        """Insert an order record (used by OrderManager)."""
        self.insert_order(row)

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------

    def insert_position(self, row: dict) -> None:
        with self._session() as sess:
            sess.add(Position(**row))
            sess.commit()

    # ------------------------------------------------------------------
    # Decisions
    # ------------------------------------------------------------------

    def insert_decision(self, row: dict) -> None:
        if "full_record" in row and isinstance(row["full_record"], dict):
            row = dict(row)
            row["full_record"] = json.dumps(row["full_record"])
        with self._session() as sess:
            sess.add(Decision(**row))
            sess.commit()

    def save_decision(self, **kwargs) -> None:
        """Insert a decision from keyword arguments (used by DecisionLogger)."""
        self.insert_decision(kwargs)

    def get_decisions(self, limit: int = 100) -> list[dict]:
        with self._session() as sess:
            rows = (
                sess.query(Decision)
                .order_by(Decision.timestamp.desc())
                .limit(limit)
                .all()
            )
            result = []
            for r in rows:
                d = {k: v for k, v in r.__dict__.items() if not k.startswith("_")}
                if d.get("full_record"):
                    try:
                        d["full_record"] = json.loads(d["full_record"])
                    except Exception:
                        pass
                result.append(d)
            return result

    # ------------------------------------------------------------------
    # Trades
    # ------------------------------------------------------------------

    def insert_trade(self, row: dict) -> None:
        with self._session() as sess:
            sess.add(Trade(**row))
            sess.commit()

    def get_trades(self, limit: int = 500) -> list[dict]:
        with self._session() as sess:
            rows = (
                sess.query(Trade)
                .order_by(Trade.timestamp.desc())
                .limit(limit)
                .all()
            )
            return [{k: v for k, v in r.__dict__.items() if not k.startswith("_")} for r in rows]
