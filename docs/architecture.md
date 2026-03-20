# Aegis 시스템 아키텍처

## 개요

Aegis는 Binance USDS-M Futures에서 BTC/USDT 영구선물을 대상으로 하는 AI 기반 양방향(롱/숏) 자동매매 시스템입니다.

## 시스템 구성도

```
┌─────────────────────────────────────────────────────────────────┐
│                        Docker Compose                           │
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────────┐       │
│  │ aegis-trader │  │  aegis-api  │  │ aegis-backoffice │       │
│  │ (Orchestrator│  │  (FastAPI)  │  │   (Streamlit)    │       │
│  │  :scheduler) │  │   :8000     │  │     :8501        │       │
│  └──────┬───────┘  └──────┬──────┘  └────────┬─────────┘       │
│         │                 │                   │                 │
│         └────────┬────────┴───────────────────┘                 │
│                  │                                               │
│           ┌──────▼──────┐                                       │
│           │  SQLite DB  │                                       │
│           │ data/aegis.db│                                       │
│           └─────────────┘                                       │
└─────────────────────────────────────────────────────────────────┘
```

## 데이터 흐름

```
Binance Vision (히스토리컬)  ──┐
                               ├──► Feature Engineering ──► 앙상블 모델 ──► 시그널 변환 ──► 리스크 체크 ──► 주문 실행
CCXT WebSocket (실시간)     ──┘     (20+ 피처)            (LightGBM      (Z-score      (2단계        (Binance
                                                           + TRA          정규화)        사전/실시간)   Futures
                                                           + ADARNN)                                   Testnet)
```

## 핵심 모듈

### 데이터 파이프라인 (`data/`)
| 모듈 | 역할 |
|------|------|
| `binance_vision.py` | Binance Vision에서 히스토리컬 OHLCV 데이터 다운로드 |
| `collector.py` | CCXT WebSocket 기반 실시간 캔들 수집 |
| `storage.py` | SQLAlchemy + SQLite 저장소 (candles, trades, decisions, signals, positions, funding_rates, risk_events) |
| `feature_engineer.py` | 모멘텀, 변동성, 볼륨, 추세, 마이크로스트럭처, Futures 전용 피처 생성 |
| `realtime_feed.py` | Binance Futures WebSocket 실시간 피드 |

### AI 모델 (`models/`)
| 모듈 | 역할 |
|------|------|
| `lgbm_model.py` | LightGBM 베이스라인 모델 |
| `tra_model.py` | Temporal Routing Adaptor — 시장 레짐별 predictor 라우팅 |
| `adarnn_model.py` | Adaptive RNN — 시계열 분포 변화에 강건한 예측 |
| `ensemble.py` | 스태킹 앙상블 (3개 모델 → 메타 LightGBM) |
| `trainer.py` | 학습/리트레이닝 파이프라인 (rolling 7일 주기) |

### 전략 (`strategy/`)
| 모듈 | 역할 |
|------|------|
| `signal_converter.py` | 예측값 → Z-score → 포지션 시그널 변환 |
| `position_manager.py` | 목표 포지션 vs 현재 포지션 비교 → 주문 생성 |
| `regime_detector.py` | TRA 라우터 가중치 기반 레짐 감지 (TRENDING/RANGING/VOLATILE) |
| `decision_logger.py` | 모든 의사결정 감사 추적 (EXECUTE/SKIP/REJECTED) |

### 리스크 관리 (`risk/`)
| 모듈 | 역할 |
|------|------|
| `risk_engine.py` | 2단계 리스크: Stage 1(사전 체크) + Stage 2(실시간 모니터링) |
| `position_limits.py` | 포지션 한도 체크 (MAX_POSITION_RATIO) |
| `drawdown_monitor.py` | 드로다운 레벨별 행동 (5% 경고, 8% 축소, 10% 정지) |

### 실행 (`execution/`)
| 모듈 | 역할 |
|------|------|
| `binance_executor.py` | CCXT 기반 Binance Futures 주문 실행 (Testnet/Mainnet 자동 분기) |
| `paper_trader.py` | 가상 거래 시뮬레이터 (동일 인터페이스) |
| `order_manager.py` | 주문 큐 관리, 미체결 주문 추적 |

### API (`api/`)
FastAPI 서버 — 13개 라우터, 27개 엔드포인트:
- `health`, `positions`, `metrics`, `trades`, `funding`, `signals`, `decisions`
- `analytics` (pnl-summary, equity-curve, performance, attribution)
- `models`, `risk`, `backtests`, `system`, `control`

### 백오피스 (`backoffice/`)
Streamlit 멀티페이지 대시보드 — 8개 페이지:
1. Live Dashboard — 실시간 포지션/PnL 모니터링
2. Decision Log — 의사결정 감사 추적
3. Trade Journal — 개별 거래 분석
4. PnL Analytics — 수익률 분석 + 귀인 분석
5. Model Monitor — 모델 성능 추적 + 리트레이닝 제어
6. Risk Dashboard — 리스크 현황
7. Backtest Viewer — 백테스트 결과 비교
8. System Ops — 시스템 운영 + 디버깅

## 환경 설정

| 설정 | 기본값 | 설명 |
|------|--------|------|
| `USE_TESTNET` | `True` | Testnet/Mainnet 분기 (⚠️ 개발 중 항상 True) |
| `TRADING_SYMBOL` | `BTC/USDT:USDT` | CCXT Futures 심볼 |
| `TIMEFRAME` | `30m` | 캔들 타임프레임 |
| `LEVERAGE` | `3` | 레버리지 (최대 10x) |
| `MARGIN_TYPE` | `isolated` | 격리 마진 |
| `MAX_POSITION_RATIO` | `0.3` | 자본 대비 최대 포지션 비율 |
| `MAX_DRAWDOWN_RATIO` | `0.10` | 최대 드로다운 (초과 시 전체 청산) |

## Docker 서비스

```yaml
services:
  aegis-trader:    # 메인 트레이딩 루프 (orchestrator)
  aegis-api:       # FastAPI REST API (:8000)
  aegis-backoffice: # Streamlit 대시보드 (:8501)
```

모든 서비스는 `aegis-net` 브릿지 네트워크에서 통신하며, `data/`와 `models/saved/` 볼륨을 공유합니다.
