# Aegis — AI Crypto Futures Auto-Trading System

> OMC Autopilot Prompt | Project: **Aegis** (`aegis-trading`)

## MASTER PLAN

### 프로젝트 개요

**Aegis**(아이기스)는 Binance USDS-M Futures에서 BTC/USDT 영구선물(perpetual)을 대상으로 30분~1시간 타임프레임의 AI 기반 양방향(롱/숏) 자동매매 시스템이다.
Qlib의 LightGBM + TRA + ADARNN 앙상블 모델로 시그널을 생성하고, CCXT를 통해 실제 주문을 실행한다.
2단계 리스크 관리 시스템(포지션 한도 + 드로다운 컷)을 내장한다.
과거 거래 데이터는 Binance Vision(https://data.binance.vision)에서 다운로드하여 사용하며, 백테스팅 및 실제 거래 테스트는 반드시 Binance Futures Testnet에서만 수행한다. Mainnet 거래는 이 프로젝트의 자동화 범위에 포함하지 않는다.

### 환경 가정

- `.env` 파일에 `CT_BINANCE_API_KEY`와 `CT_BINANCE_API_SECRET`가 저장되어 있음 (Mainnet Futures API 키)
- Binance Futures Testnet 키도 `CT_BINANCE_TESTNET_API_KEY`, `CT_BINANCE_TESTNET_API_SECRET`로 저장
  - Testnet 키 발급: https://testnet.binancefuture.com 에서 GitHub 계정으로 로그인
- Mainnet API 키 발급 시 반드시 **Enable Futures** 권한 체크 필요 (선물 계정 활성화 후 API 생성)
- **Enable Withdrawals는 절대 체크하지 않는다** (출금 권한 불필요, 보안 위험)
- Python 3.10+ 환경
- GPU 없이 CPU로 학습/추론 가능하도록 설계

### 기술 스택

- **히스토리컬 데이터**: Binance Vision (https://data.binance.vision) — 공식 과거 데이터 아카이브
- **실시간 데이터**: CCXT WebSocket (Binance Futures)
- **데이터 저장**: pandas, SQLite(경량 모드) 또는 TimescaleDB
- **모델**: Qlib (LightGBM, TRA, ADARNN), PyTorch
- **실행**: CCXT (Binance USDS-M Futures) — ⚠️ Spot이 아닌 Futures 사용. 롱/숏 양방향 포지션 필요.
- **서버**: FastAPI (추론 API + 모니터링 대시보드)
- **운영**: Docker Compose, APScheduler, python-telegram-bot
- **테스트**: pytest, Binance Futures Testnet (⚠️ 모든 거래 테스트는 Testnet에서만 수행)

### ⚠️ 왜 Futures인가 (Spot이 아닌 이유)

이 시스템은 시장 방향에 따라 롱/숏 양방향 포지션을 잡는 전략이다.
Spot에서는 숏(공매도)이 불가능하여 전략의 절반을 실행할 수 없다.
따라서 반드시 Binance USDS-M Futures를 사용한다.

| 항목 | Spot | Futures (이 프로젝트) |
|------|------|----------------------|
| 롱 | 가능 | 가능 |
| 숏 | **불가능** | **가능** |
| 레버리지 | 1x 고정 | 1x~125x 조절 |
| 포지션 관리 | 없음 | 롱/숏 포지션 추적 |
| 펀딩레이트 | 없음 | 있음 (시그널 피처로 활용) |

### Binance Futures Testnet 정보

```
Futures Testnet 웹사이트: https://testnet.binancefuture.com
REST API Base URL:        https://testnet.binancefuture.com
WebSocket Base URL:       wss://stream.binancefuture.com
API 키 발급:               GitHub 계정으로 로그인 후 자동 발급
테스트 잔고:               자동 충전 (USDT 등)
```

---

## Phase 1: Aegis 프로젝트 초기화 및 데이터 파이프라인

### 목표
프로젝트 구조를 생성하고, Binance에서 히스토리컬 + 실시간 캔들 데이터를 수집하는 파이프라인을 구축한다.

### 상세 작업

```
1-1. 프로젝트 디렉토리 구조 생성:

aegis/
├── .env                          # API 키 (gitignore 대상)
├── .env.example                  # 키 템플릿
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml                # dependencies 관리 (name = "aegis-trading")
├── README.md
├── config/
│   ├── settings.py               # 전역 설정 (Pydantic BaseSettings)
│   ├── symbols.py                # 거래 대상 심볼 목록
│   └── risk_params.py            # 리스크 파라미터
├── data/
│   ├── binance_vision.py         # Binance Vision 히스토리컬 데이터 다운로더
│   ├── collector.py              # 실시간 캔들 데이터 수집기 (CCXT WebSocket)
│   ├── storage.py                # SQLite/TimescaleDB 저장소
│   ├── feature_engineer.py       # 피처 생성 (Qlib Alpha158 호환)
│   └── realtime_feed.py          # WebSocket 실시간 데이터 피드
├── models/
│   ├── base.py                   # 모델 인터페이스 추상 클래스
│   ├── lgbm_model.py             # LightGBM 모델
│   ├── tra_model.py              # TRA 모델 (Qlib 기반)
│   ├── adarnn_model.py           # ADARNN 모델 (Qlib 기반)
│   ├── ensemble.py               # 앙상블 (스태킹 메타 모델)
│   └── trainer.py                # 학습/리트레이닝 파이프라인
├── strategy/
│   ├── signal_converter.py       # 예측값 → 포지션 시그널 변환
│   ├── position_manager.py       # 포지션 크기 계산 + 관리
│   ├── regime_detector.py        # TRA 라우터 기반 레짐 감지
│   └── decision_logger.py        # 의사결정 감사 추적 (audit trail)
├── risk/
│   ├── risk_engine.py            # 2단계 리스크 관리 시스템
│   ├── position_limits.py        # 포지션 한도 체크
│   └── drawdown_monitor.py       # 드로다운 모니터링 + 자동 컷
├── execution/
│   ├── binance_executor.py       # CCXT 기반 Binance 주문 실행
│   ├── order_manager.py          # 주문 생성/취소/상태 추적
│   └── paper_trader.py           # 페이퍼 트레이딩 시뮬레이터
├── api/
│   ├── main.py                   # FastAPI 엔트리포인트
│   ├── routes/
│   │   ├── health.py             # 헬스체크
│   │   ├── signals.py            # 시그널 조회 API
│   │   ├── positions.py          # 포지션 조회/관리 API
│   │   ├── decisions.py          # 의사결정 로그 조회 API
│   │   ├── analytics.py          # 수익률/성과 분석 API
│   │   └── control.py            # 시스템 시작/중지/설정 API
│   └── websocket.py              # 실시간 상태 WebSocket
├── backoffice/                   # ⭐ 백오피스 관리 대시보드
│   ├── app.py                    # Streamlit 메인 엔트리포인트
│   ├── pages/
│   │   ├── 01_live_dashboard.py  # 실시간 운영 대시보드
│   │   ├── 02_decision_log.py    # 의사결정 감사 추적 뷰어
│   │   ├── 03_trade_journal.py   # 거래 일지 + 개별 트레이드 분석
│   │   ├── 04_pnl_analytics.py   # 수익률 분석 + 귀인 분석
│   │   ├── 05_model_monitor.py   # 모델 성능 모니터링
│   │   ├── 06_risk_dashboard.py  # 리스크 현황 대시보드
│   │   ├── 07_backtest_viewer.py # 백테스트 결과 비교 뷰어
│   │   └── 08_system_ops.py      # 시스템 운영 + 디버깅
│   └── components/
│       ├── charts.py             # 공통 차트 컴포넌트
│       └── filters.py            # 날짜/심볼 필터 컴포넌트
├── analytics/                    # 분석 엔진
│   ├── pnl_calculator.py         # 수익률 계산 (레버리지, 펀딩비용, 수수료 반영)
│   ├── performance_metrics.py    # Sharpe, Sortino, Calmar, 승률, 기대수익 등
│   ├── attribution.py            # PnL 귀인 분석 (모델별, 레짐별, 시간대별)
│   └── report_generator.py       # 일간/주간/월간 리포트 자동 생성
├── monitor/
│   ├── telegram_bot.py           # Telegram 알림
│   └── metrics.py                # 실시간 지표 수집
├── scheduler/
│   └── orchestrator.py           # APScheduler 기반 메인 루프
├── tests/
│   ├── test_data_collector.py
│   ├── test_feature_engineer.py
│   ├── test_models.py
│   ├── test_signal_converter.py
│   ├── test_decision_logger.py   # 의사결정 감사 추적 테스트
│   ├── test_risk_engine.py
│   ├── test_binance_executor.py  # Testnet 실제 거래 테스트
│   ├── test_paper_trader.py
│   ├── test_analytics.py         # PnL 계산, 성과 지표, 귀인 분석 정확도 테스트
│   ├── test_mainnet_readiness.py # USE_TESTNET=False 아키텍처 분기 검증 (mock only)
│   └── test_e2e_pipeline.py      # 전체 파이프라인 E2E 테스트
└── scripts/
    ├── download_binance_vision.py # Binance Vision에서 히스토리컬 데이터 다운로드
    ├── backfill_data.py          # 다운로드된 데이터를 DB에 적재
    ├── train_models.py           # 모델 학습 스크립트
    └── run_backtest.py           # 백테스트 실행 (Testnet Only)

1-2. pyproject.toml에 의존성 정의:
    - ccxt>=4.0
    - qlib (pip install pyqlib)
    - lightgbm
    - torch (CPU 버전)
    - pandas, numpy, scikit-learn
    - fastapi, uvicorn
    - apscheduler
    - python-telegram-bot
    - python-dotenv
    - pydantic-settings
    - pytest, pytest-asyncio
    - sqlalchemy (SQLite 백엔드)
    - websockets
    - requests (Binance Vision 다운로드용)
    - tqdm (다운로드 진행률 표시)
    - streamlit (백오피스 대시보드)
    - plotly (인터랙티브 차트)

1-3. config/settings.py 구현:
    - .env에서 CT_BINANCE_API_KEY, CT_BINANCE_API_SECRET 로드
    - CT_BINANCE_TESTNET_API_KEY, CT_BINANCE_TESTNET_API_SECRET 로드
    - TRADING_SYMBOL = "BTC/USDT:USDT" (CCXT Futures 심볼 표기법)
    - TIMEFRAME = "30m" (기본값, "1h"로 변경 가능)

    [Futures 전용 설정]
    - MARKET_TYPE = "future" (CCXT defaultType — ⚠️ "spot"으로 변경하지 않는다)
    - LEVERAGE = 3 (기본 레버리지 3x. 최대 허용 10x. 초보 단계에서는 1~3x 권장)
    - MARGIN_TYPE = "isolated" (격리 마진. cross 마진은 전체 계좌가 청산 위험에 노출되므로 사용하지 않는다)
    - POSITION_MODE = "one-way" (단방향 포지션 모드. hedge 모드보다 구현이 단순)

    [리스크 설정]
    - MAX_POSITION_RATIO = 0.3 (자본의 최대 30%)
    - MAX_DAILY_LOSS_RATIO = 0.05 (일일 최대 손실 5%)
    - MAX_DRAWDOWN_RATIO = 0.10 (최대 드로다운 10%)
    - RISK_REWARD_RATIO = 2.0
    - MIN_SIGNAL_THRESHOLD = 1.0 (Z-score 최소값)

    [환경 설정]
    - USE_TESTNET = True (⚠️ 개발/테스트 중에는 항상 True로 유지. 코드에서 자동으로 False로 변경하지 않는다.)
      단, 아키텍처는 USE_TESTNET=False 시 Mainnet에서 즉시 운영 가능하도록 설계해야 한다.
      USE_TESTNET 값에 따라 아래 항목이 자동 분기되어야 한다:
        - API 키: True → CT_BINANCE_TESTNET_*, False → CT_BINANCE_API_*
        - CCXT sandbox 모드: True → sandbox=True, False → sandbox=False
        - 로그 태그: True → [TESTNET], False → [MAINNET]
        - Telegram 알림 태그: 동일하게 분기
        - 주문 실행 전 확인: False일 때 추가 safety confirmation 로직 활성화
    - BINANCE_VISION_BASE_URL = "https://data.binance.vision" (히스토리컬 데이터 소스)
    - TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (선택)

    [CCXT 초기화 예시 — settings 기반]
    ```python
    import ccxt
    exchange = ccxt.binance({
        'apiKey': api_key,       # USE_TESTNET에 따라 분기
        'secret': api_secret,    # USE_TESTNET에 따라 분기
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',          # ⚠️ 반드시 'future'
            'adjustForTimeDifference': True,
        }
    })
    if use_testnet:
        exchange.set_sandbox_mode(True)

    # Futures 초기 설정 (최초 1회)
    exchange.fapiPrivate_post_leverage({
        'symbol': 'BTCUSDT',
        'leverage': LEVERAGE,        # 3x
    })
    exchange.fapiPrivate_post_margintype({
        'symbol': 'BTCUSDT',
        'marginType': 'ISOLATED',    # 격리 마진
    })
    ```

1-4. data/binance_vision.py 구현 — 히스토리컬 데이터 다운로더:
    ⚠️ 모든 과거 거래 데이터는 Binance Vision(https://data.binance.vision)에서 다운로드한다.
    CCXT fetch_ohlcv()는 히스토리컬 백필에 사용하지 않는다. Binance Vision이 공식 아카이브이며
    데이터 품질이 가장 높고, rate limit 없이 대량 다운로드가 가능하다.

    - 다운로드 URL 패턴:
        ⚠️ Futures 데이터를 다운로드한다 (spot이 아닌 futures 경로 사용)
        월간 데이터: https://data.binance.vision/data/futures/um/monthly/klines/{symbol}/{interval}/{symbol}-{interval}-{YYYY}-{MM}.zip
        일간 데이터: https://data.binance.vision/data/futures/um/daily/klines/{symbol}/{interval}/{symbol}-{interval}-{YYYY}-{MM}-{DD}.zip
    - 지원 인터벌: 30m, 1h (설정에 따라)
    - 심볼: BTCUSDT (Binance Vision은 슬래시 없는 심볼명 사용, Futures um = USDS-M)
    - 다운로드 흐름:
        1. 시작일~종료일 범위의 월간 zip 파일 URL 목록 생성
        2. 각 zip 다운로드 → 압축 해제 → CSV 파싱
        3. CSV 컬럼: open_time, open, high, low, close, volume, close_time,
           quote_volume, count, taker_buy_volume, taker_buy_quote_volume, ignore
        4. DataFrame으로 병합, 타임스탬프 정렬, 중복 제거
    - 체크섬 검증: 각 zip과 함께 제공되는 .CHECKSUM 파일로 SHA256 검증
    - 재시도 로직: 다운로드 실패 시 3회 재시도 (지수 백오프)
    - 캐싱: 이미 다운로드된 zip은 data/raw/ 에 보관, 재다운로드 방지
    - 최소 6개월~최대 2년치 데이터 다운로드 지원

1-5. data/collector.py 구현 — 실시간 데이터 수집기:
    ⚠️ collector.py는 실시간(라이브) 캔들 수집 전용이다. 히스토리컬 데이터에는 사용하지 않는다.
    ⚠️ CCXT 초기화 시 반드시 defaultType='future' 설정.
    - CCXT의 watchOHLCV 또는 Binance Futures WebSocket으로 실시간 캔들 구독
    - 새 캔들 완성 시 storage에 저장 + 콜백 호출
    - 최근 N개 캔들 조회 메서드 (피처 계산용)
    - 펀딩레이트 수집: exchange.fetchFundingRate('BTC/USDT:USDT') → 8시간 간격 펀딩레이트 저장
    - 미결제약정(Open Interest) 수집: 시그널 피처로 활용
    - Binance Vision 데이터와 실시간 데이터를 이음매 없이 연결하는 로직:
        시스템 시작 시 Binance Vision 마지막 타임스탬프 이후부터 CCXT fetch_ohlcv로 갭 채우기

1-6. data/storage.py 구현:
    - SQLAlchemy + SQLite 기반 로컬 저장소
    - candles 테이블: timestamp, open, high, low, close, volume
    - funding_rates 테이블: timestamp, symbol, funding_rate, mark_price
    - signals 테이블: timestamp, model_name, prediction, position_signal
    - orders 테이블: timestamp, side, price, amount, status, order_id, leverage
    - positions 테이블: timestamp, side, entry_price, size, unrealized_pnl, liquidation_price
    - decisions 테이블: timestamp, candle_id, decision, direction, z_score, regime, reason, full_record(JSON)
    - trades 테이블: timestamp, side, entry_price, exit_price, pnl, funding_cost
    - upsert 지원 (중복 타임스탬프 처리)

1-7. data/feature_engineer.py 구현:
    크립토 30분/1시간 타임프레임에 최적화된 피처셋:

    [모멘텀/리버설]
    - return_1h, return_4h, return_12h, return_24h (수익률)
    - return_zscore_24h (24시간 수익률의 Z-score)
    - roc_6, roc_12, roc_24 (Rate of Change)

    [변동성]
    - realized_vol_12h, realized_vol_24h
    - atr_14 (Average True Range, 14봉)
    - parkinson_vol_24h (Parkinson 변동성)
    - bollinger_width_20 (볼린저 밴드 폭)

    [볼륨]
    - volume_ratio_12h (현재 볼륨 / 12시간 이동평균)
    - vwap_deviation (VWAP 대비 괴리율)
    - obv_change_12h (OBV 변화율)

    [추세]
    - ema_cross_12_26 (EMA 12/26 교차 신호)
    - macd_histogram
    - adx_14 (Average Directional Index)

    [마이크로스트럭처]
    - spread_avg_1h (호가 스프레드 평균, 가능시)
    - high_low_ratio (고가/저가 비율)
    - close_position (캔들 내 종가 위치: (C-L)/(H-L))

    [Futures 전용 피처] ⚠️ Spot에는 없는 선물 고유 데이터
    - funding_rate (8시간 간격 펀딩레이트 — 시장 센티멘트의 핵심 프록시)
    - funding_rate_ma_3 (최근 3회 펀딩레이트 이동평균)
    - basis (선물가 - 현물가 괴리율, 가능시)
    - open_interest_change_24h (미결제약정 24시간 변화율)
    - long_short_ratio (롱/숏 비율, Binance API로 수집 가능시)
    - taker_buy_sell_ratio (테이커 매수/매도 비율)

    모든 피처는 NaN 처리, forward-fill 후 dropna 적용.
    Qlib의 Alpha158 포맷과 호환되도록 구성.

1-8. data/realtime_feed.py 구현:
    ⚠️ Binance Futures WebSocket 사용 (Spot이 아님)
    - CCXT의 watchOHLCV (defaultType='future') 또는 Binance Futures WebSocket으로 실시간 캔들 구독
    - Futures 전용 스트림 추가 구독:
        - wss://fstream.binance.com/ws/btcusdt@markPrice (마크 가격 + 펀딩레이트)
        - wss://fstream.binance.com/ws/btcusdt@forceOrder (청산 이벤트)
    - 새 캔들 완성 시 콜백 호출 (signal_converter로 전달)
    - 재연결 로직 포함 (연결 끊김 시 자동 재시도, 최대 5회, 지수 백오프)
    - heartbeat 체크 (30초 간격)

1-9. scripts/download_binance_vision.py 구현:
    - CLI 스크립트: 심볼, 인터벌, 시작일, 종료일을 인자로 받음
    - 예시: python scripts/download_binance_vision.py --symbol BTCUSDT --interval 30m --start 2024-01-01 --end 2025-03-01
    - binance_vision.py를 호출하여 데이터 다운로드
    - 다운로드 완료 후 storage에 자동 적재
    - 진행률 표시 (tqdm)
    - 데이터 무결성 리포트 출력 (총 캔들 수, 시작/종료 시각, 결측 구간)
```

### 검증 기준 (Phase 1 완료 조건)

```
✅ Binance Vision에서 BTC/USDT 30분봉 최소 6개월치 데이터 다운로드 성공
✅ 다운로드된 데이터의 SHA256 체크섬 검증 통과
✅ SQLite에 데이터 저장 및 조회 정상 작동 (타임스탬프 연속성 확인)
✅ feature_engineer가 20개+ 피처를 NaN 없이 생성
✅ realtime_feed가 Binance WebSocket에 연결되어 새 캔들 수신 확인
✅ Binance Vision 데이터와 실시간 데이터 간 이음매 없는 연결 확인
✅ pytest test_data_collector.py, test_feature_engineer.py 전부 PASS
```

---

## Phase 2: AI 모델 학습 파이프라인

### 목표
LightGBM 베이스라인 모델을 학습하고, TRA/ADARNN을 추가하여 앙상블을 구성한다.

### 상세 작업

```
2-1. models/base.py — 모델 인터페이스:
    class BaseModel(ABC):
        def train(self, X_train, y_train, X_val, y_val) -> None
        def predict(self, X) -> np.ndarray  # 연속값 수익률 예측
        def save(self, path: str) -> None
        def load(self, path: str) -> None
        def get_feature_importance(self) -> dict  # 선택적

2-2. models/lgbm_model.py — LightGBM 모델:
    - BaseModel 상속
    - 하이퍼파라미터:
        num_leaves=31, learning_rate=0.05, n_estimators=500,
        min_child_samples=20, subsample=0.8, colsample_bytree=0.8,
        reg_alpha=0.1, reg_lambda=0.1
    - early_stopping_rounds=50 (val loss 기준)
    - feature_importance() 제공
    - 학습 시 IC(Information Coefficient) 출력

2-3. models/tra_model.py — Temporal Routing Adaptor:
    - Qlib의 TRA 구현체를 래핑하거나, 직접 PyTorch로 구현
    - 핵심 구조:
        - Router Network: 현재 시장 상태 입력 → K개 predictor 중 선택 (K=3~5)
        - Predictor Network: 각각 독립적인 LSTM/GRU 기반 예측기
        - 최종 출력: 라우터 가중치 × 각 predictor 출력의 가중합
    - 라우터 가중치를 외부에서 조회 가능하게 expose (레짐 감지용)
    - lookback_window = 48 (30분봉 기준 24시간)

2-4. models/adarnn_model.py — ADARNN:
    - 시계열을 N개 구간으로 분할
    - 구간 간 분포 차이를 minimize하는 adversarial loss 추가
    - 기본 backbone: GRU
    - num_segments = 5, hidden_size = 64

2-5. models/ensemble.py — 스태킹 앙상블:
    - 3개 모델(LightGBM, TRA, ADARNN)의 예측값을 메타 피처로 사용
    - 메타 모델: 소형 LightGBM (num_leaves=8, n_estimators=50)
    - 학습 방식: 시간 기반 5-fold CV (미래 데이터 누수 방지)
        - Fold 1: Train 1-2월, Val 3월
        - Fold 2: Train 1-3월, Val 4월
        - ...
    - out-of-fold prediction으로 메타 모델 학습
    - 최종 출력: 앙상블 예측값 (연속값)

2-6. models/trainer.py — 학습/리트레이닝:
    - train_all_models(): 3개 모델 순차 학습
    - retrain_rolling(): N일마다 윈도우 이동하며 재학습
        - 기본: 7일(30분봉 기준 336개 캔들 추가) 마다 리트레이닝
        - 학습 윈도우: 최근 90일
        - 검증 윈도우: 최근 7일
    - evaluate(): IC, Rank IC, 방향 정확도, Sharpe ratio 계산
    - 모델 저장: models/saved/ 에 버전별 저장
```

### 검증 기준 (Phase 2 완료 조건)

```
✅ LightGBM이 6개월 데이터로 학습 완료, IC > 0.02 (val set 기준)
✅ TRA 학습 완료, 라우터 가중치 추출 가능
✅ ADARNN 학습 완료
✅ 앙상블 모델이 개별 모델 대비 IC 개선 확인
✅ 리트레이닝이 자동으로 돌아가는지 확인
✅ pytest test_models.py PASS
```

---

## Phase 3: 시그널 변환 및 리스크 관리

### 목표
모델 예측값을 실제 롱/숏 포지션으로 변환하고, 2단계 리스크 관리 시스템을 구축한다.

### 상세 작업

```
3-1. strategy/signal_converter.py:
    - 모델 예측값(연속값) → Z-score 정규화
    - 포지션 비율 계산:
        z = prediction / rolling_std(predictions, window=48)
        if abs(z) < MIN_SIGNAL_THRESHOLD: position = 0  (관망)
        else: position = clip(z * scale_factor, -1.0, +1.0)
    - 거래비용 필터: |expected_return| < 2 * fee_rate 이면 무시
    - 방향 전환 필터: 이전 시그널과 반대 방향이면 연속 2회 확인 후 전환
    - 최소 보유 시간: 포지션 진입 후 최소 2캔들(1시간) 유지

3-2. strategy/position_manager.py:
    - 현재 Futures 포지션 추적 (long/short/flat, 수량, 진입가, 미실현 PnL)
    - 목표 포지션과 현재 포지션 비교 → 차이만큼 주문 생성
        - 목표: 롱 0.5 → 현재: flat → 롱 0.5 진입
        - 목표: 숏 0.3 → 현재: 롱 0.5 → 롱 0.5 청산 + 숏 0.3 진입
        - 목표: flat → 현재: 숏 0.3 → 숏 0.3 청산
    - 레버리지 관리 (기본값: settings.LEVERAGE, 최대 10x)
    - 격리 마진(isolated margin) 기준 청산가격(liquidation price) 모니터링
    - 펀딩레이트 비용 추적: 포지션 보유 중 8시간 간격으로 발생하는 펀딩 비용 누적
    - 평균 진입가 계산
    - PnL 실시간 계산 (레버리지 반영: PnL = size × (current - entry) × leverage)

3-3. strategy/regime_detector.py:
    - TRA 라우터 가중치로 현재 레짐 분류:
        - TRENDING (추세장): 모멘텀 기반 predictor 활성
        - RANGING (횡보장): 평균회귀 predictor 활성
        - VOLATILE (폭락/급등장): 방어적 predictor 활성
    - 레짐별 전략 파라미터 오버라이드:
        TRENDING:  max_position=1.0, stop_loss=3%, take_profit=6%
        RANGING:   max_position=0.5, stop_loss=1.5%, take_profit=3%
        VOLATILE:  max_position=0.3, stop_loss=1%, take_profit=2%

3-4. risk/risk_engine.py — 2단계 리스크 관리:

    [Stage 1: 사전 체크 — 주문 전]
    - 포지션 한도 체크: 총 포지션 <= MAX_POSITION_RATIO * 계좌 잔고
    - 단일 주문 크기 제한: 주문 금액 <= 계좌 잔고의 10%
    - 일일 거래 횟수 제한: 최대 20회/일
    - 일일 손실 한도: 당일 실현 손실 + 미실현 손실 <= MAX_DAILY_LOSS_RATIO * 시작 잔고
    - 연속 손실 체크: 5회 연속 손실 시 거래 중지 (30분 쿨다운)

    [Stage 2: 실시간 모니터링 — 포지션 보유 중]
    - 스탑로스: 레짐별 동적 스탑로스 (regime_detector 연동)
    - 테이크프로핏: 리스크:리워드 비율 적용
    - 트레일링 스탑: 이익 2% 이상 시 활성화, 고점 대비 1% 하락 시 청산
    - 최대 드로다운: 전고점 대비 MAX_DRAWDOWN_RATIO 이상 하락 시 전체 청산
    - ⚠️ 청산가격 접근 경고 (Futures 전용):
        마크 가격이 청산가격의 80% 이내 접근 시 → Telegram 긴급 알림 + 포지션 50% 축소
        마크 가격이 청산가격의 90% 이내 접근 시 → 전체 포지션 즉시 시장가 청산
    - 펀딩레이트 리스크:
        다음 펀딩레이트가 ±0.1% 이상일 때 경고 (포지션 방향과 반대 펀딩은 비용 발생)
    - 긴급 청산: 특정 임계치 초과 시 모든 포지션 즉시 마켓 주문으로 청산

3-5. risk/drawdown_monitor.py:
    - 계좌 잔고의 전고점(equity high watermark) 추적
    - 실시간 드로다운 계산: drawdown = (hwm - current) / hwm
    - 드로다운 레벨별 행동:
        5% → Telegram 경고 알림
        8% → 신규 포지션 금지, 기존 포지션 50% 축소
        10% → 전체 포지션 청산, 시스템 일시 정지 (수동 재개 필요)

3-6. strategy/decision_logger.py — 의사결정 감사 추적 (Audit Trail):
    ⚠️ 이 컴포넌트는 백오피스 운영의 핵심이다. 모든 거래 의사결정의 "왜?"를 기록한다.
    "왜 이 거래를 했지?", "왜 이 시그널을 무시했지?"를 추적할 수 없으면 시스템 개선이 불가능하다.

    매 캔들마다 아래 구조의 DecisionRecord를 생성하여 DB(decisions 테이블)에 저장:

    DecisionRecord 구조:
    - timestamp, candle_id
    - market_snapshot: price, volume_24h, funding_rate, regime, regime_confidence
    - model_predictions: 모델별 raw 예측값, z_score, TRA active_router + router_weights
    - top_features: 상위 10개 피처명 + 값 (어떤 피처가 예측에 기여했는지)
    - signal: raw_position, direction(LONG/SHORT/FLAT), size_ratio, 각 필터 통과 여부
    - risk_check: Stage1 통과 여부 + 항목별 상세, Stage2 현황(drawdown, liq 거리, SL/TP 레벨)
    - decision: EXECUTE / SKIP / REJECTED_BY_RISK / REDUCE / CLOSE
    - decision_reason: 사람이 읽을 수 있는 한글 설명 문자열
      예) "앙상블 Z=1.9 > threshold 1.0, 리스크 전부 통과, TRENDING 레짐 롱 진입"
      예) "앙상블 Z=0.4 < threshold 1.0, 시그널 강도 부족 관망"
      예) "Stage 1 거부: 일일 손실 한도 4.8%/5% 근접, 신규 포지션 차단"
    - execution (EXECUTE일 때만): order_id, side, amount, intended_price, filled_price, slippage_bps, fee, latency_ms

    SKIP/REJECTED 포함 모든 케이스를 빠짐없이 기록한다.
    이 데이터가 백오피스 의사결정 뷰어의 데이터 소스가 된다.
```

### 검증 기준 (Phase 3 완료 조건)

```
✅ signal_converter가 모델 예측값으로 정확한 Z-score 포지션 생성
✅ 거래비용 필터가 작은 시그널 무시 확인
✅ risk_engine Stage 1이 한도 초과 주문을 거부
✅ risk_engine Stage 2가 스탑로스/테이크프로핏 정상 작동
✅ drawdown_monitor가 드로다운 레벨별 행동 정확히 수행
✅ decision_logger가 매 캔들마다 DecisionRecord를 DB에 저장
✅ EXECUTE / SKIP / REJECTED 모든 케이스에서 decision_reason 기록 확인
✅ pytest test_signal_converter.py, test_risk_engine.py, test_decision_logger.py PASS
```

---

## Phase 4: Futures 주문 실행 엔진 + Binance Futures Testnet 연동

### 목표
CCXT를 통해 Binance Futures Testnet에서 롱/숏 주문을 넣고 체결을 확인한다.
⚠️ 이 Phase의 모든 거래 실행은 Futures Testnet에서만 수행한다.
단, USE_TESTNET=False 전환 시 Mainnet Futures에서 즉시 운영 가능하도록 아키텍처를 설계한다.

### 상세 작업

```
4-1. execution/binance_executor.py:
    - CCXT Binance 인스턴스 초기화:
        - USE_TESTNET 설정값에 따라 자동 분기:
            True  → sandbox=True, CT_BINANCE_TESTNET_API_KEY/SECRET 사용
            False → sandbox=False, CT_BINANCE_API_KEY/SECRET 사용
        - 현재 개발 단계에서는 USE_TESTNET=True만 사용
        - ⚠️ Mainnet safety guard (USE_TESTNET=False일 때만 활성화):
            - 시스템 시작 시 "⚠️ MAINNET MODE — 실제 자산이 거래됩니다" 경고 로그 3회 출력
            - 첫 주문 실행 전 5초 대기 + 로그 출력 ("Mainnet 주문 실행 대기 중...")
            - 단일 주문 최대 금액 제한 강화 (계좌의 5% 이하)
            - 일일 최대 거래 횟수 축소 (10회)
    - 환경 인식 로깅:
        - USE_TESTNET=True  → 모든 로그에 [TESTNET] 태그
        - USE_TESTNET=False → 모든 로그에 [MAINNET] 태그
    - 주요 메서드:
        [Futures 초기 설정]
        - initialize_futures() → 레버리지 설정, 마진 타입 설정 (최초 1회)
            exchange.fapiPrivate_post_leverage({'symbol': 'BTCUSDT', 'leverage': LEVERAGE})
            exchange.fapiPrivate_post_margintype({'symbol': 'BTCUSDT', 'marginType': 'ISOLATED'})
        - set_leverage(symbol, leverage) → 레버리지 동적 변경

        [잔고/포지션 조회]
        - get_balance() → Futures 계좌 USDT 잔고 조회 (available balance + unrealized PnL)
        - get_position() → 현재 Futures 포지션 조회 (side, size, entry_price, unrealized_pnl, liquidation_price)
        - get_funding_rate() → 현재 펀딩레이트 조회

        [주문 실행]
        - create_market_order(symbol, side, amount) → Futures 시장가 주문 (side: 'buy'=롱진입/숏청산, 'sell'=숏진입/롱청산)
        - create_limit_order(symbol, side, amount, price) → Futures 지정가 주문
        - close_position(symbol) → 현재 포지션 전량 청산 (시장가)
        - cancel_order(order_id) → 주문 취소
        - get_order_status(order_id) → 주문 상태 조회

        [시스템]
        - is_testnet() → bool: 현재 Testnet 모드 여부 반환
        - get_exchange_info() → 심볼별 최소주문량, 가격 단위 등 조회

    ⚠️ CCXT 초기화 시 반드시 defaultType='future' 설정:
    ```python
    exchange = ccxt.binance({
        'apiKey': api_key,
        'secret': api_secret,
        'enableRateLimit': True,
        'options': {'defaultType': 'future'}
    })
    ```
    - 에러 핸들링:
        - InsufficientFunds → 주문량 축소 후 재시도
        - NetworkError → 3회 재시도 (지수 백오프)
        - ExchangeError → 로깅 후 Telegram 알림
    - 주문 실행 결과를 storage에 기록

4-2. execution/order_manager.py:
    - 주문 큐 관리: 시그널 → 주문 생성 → 실행 → 확인
    - 미체결 주문 관리: 5분 이상 미체결 시 취소 후 시장가 재주문
    - 슬리피지 계산: 의도 가격 vs 실제 체결가 차이 기록
    - 주문 이력 DB 저장

4-3. execution/paper_trader.py:
    - 실제 거래소 연결 없이 Futures 거래 시뮬레이션
    - 현재 시장가 기준 가상 체결 (롱/숏 양방향)
    - 수수료 적용 (Futures: 0.02% maker, 0.04% taker)
    - 레버리지 반영한 PnL 계산
    - 펀딩레이트 비용 시뮬레이션 (8시간 간격)
    - 청산가격(liquidation price) 시뮬레이션
    - 잔고, 포지션, PnL 추적
    - binance_executor와 동일한 인터페이스 (Strategy Pattern / ABC)

4-4. Binance Futures Testnet 실거래 검증:
    중요: 이 단계에서 반드시 실제 Futures Testnet API를 호출하여 거래가 되는지 확인해야 한다.
    ⚠️ 모든 거래 테스트는 USE_TESTNET=True 상태에서만 수행한다.

    검증 스크립트 (tests/test_binance_executor.py):
    - USE_TESTNET=True 상태 확인 (False면 테스트 skip)
    - Futures Testnet 연결 확인 (get_balance 호출)
    - is_testnet() == True 확인
    - Futures 초기 설정 확인: 레버리지 설정, 마진 타입 설정
    - 소액 BTC/USDT 영구선물 시장가 롱 주문 실행
    - 주문 체결 확인 (status == 'closed')
    - 포지션 조회: 롱 포지션 활성 확인 (size > 0, side == 'long')
    - 시장가 포지션 청산 (close_position)
    - 청산 후 포지션 없음 확인
    - 숏 주문 테스트: 시장가 숏 진입 → 포지션 확인 → 청산
    - 에러 케이스: 잔고 초과 주문 시 적절한 에러 핸들링 확인
    - 로그에 환ê¸
```

### 검증 기준 (Phase 4 완료 조건)

```
✅ Binance Futures Testnet에 연결 성공 (잔고 조회)
✅ Futures 초기 설정 완료: 레버리지 설정, 격리 마진 설정
✅ BTC/USDT 영구선물 시장가 롱 주문이 Testnet에서 체결됨
✅ 롱 포지션 조회: side, size, entry_price, liquidation_price 확인
✅ 롱 포지션 시장가 청산 성공
✅ 숏 주문 테스트: 숏 진입 → 포지션 확인 → 청산 성공
✅ paper_trader가 binance_executor와 동일한 Autures 시뮬레이션 포함)
✅ USE_TESTNET 값에 따라 API 키, sandbox, 로그 태그가 자동 분기됨
✅ 에러 핸들링 (잔고 부족, 네트워크 에러) 테스트 PASS
✅ 모든 로그에 환경 태그([TESTNET]/[MAINNET]) 포함 확인
✅ pytest test_binance_executor.py 전체 PASS (Futures Testnet 실거래 포함)
```

---

## Phase 5: 메인 오케스트레이터 + 모니터링

### 목표
전체 파이프라인을 하나의 자동화 루프로 통합하고, 모니터링/알림 시ì

### 상세 작업

```
5-1. scheduler/orchestrator.py — 메인 루프:
    ⚠️ 개발/테스트 중에는 USE_TESTNET=True 상태에서만 운영한다.
    단, USE_TESTNET=False 전환 시에도 코드 변경 없이 동작해야 한다.

    매 30분(또는 1시간) 캔들 완성 시:
        1. 새 캔들 데이터 수신 (realtime_feed — Futures WebSocket)
        2. 피처 계산 (feature_engineer, 기반 데이터: Binance Vision + 실시간)
           ⚠️ Futures 전용 피처 포함: , 테이커 비율
        3. 3개 모델 추론 → 앙상블 시그널 생성
        4. 시그널 변환 (signal_converter → 롱/숏/관망 + 포지션 크기)
        5. 리스크 체크 (risk_engine Stage 1 + 청산가격 거리 체크)
        6. 승인된 주문 실행 (binance_executor → Futures Testnet)
        7. Futures 포지션/PnL 업데이트 (레버리지 반영)
        8. 리스크 모니터링 (risk_engine Stage 2 + 청산가격 접근 경고)
        9. 메트릭 업데이트 + Teleg알림 (환경 태그 자동 포함)

    주기적 작업:
        - 매 7일: 모델 리트레이닝 (trainer.retrain_rolling, 학습 데이터: Binance Vision + 실시간 축적분)
        - 매 8시간: 펀딩레이트 정산 체크 + 비용 기록
        - 매 1시간: 헬스체크 (거래소 API 연결, Futures 잔고, 오픈 주문, 청산가격)
        - 매일 00:00 UTC: 일일 리포트 생성 + Telegram 전송

5-2. api/main.py — FastAPI 서버:
    - GET /health → 시스템 상태 (모델, 마지막 시그널)
    - GET /signals/latest → 최근 시그널 목록
    - GET /positions → 현재 Futures 포지션 상세 (side, size, leverage, entry, liquidation_price, unrealized_pnl)
    - GET /metrics → PnL, 승률, Sharpe, 드로다운, 누적 펀딩비용
    - GET /funding-history → 펀딩레이트 정산 이력
    - POST /control/start → 자동매매 시작
    - POST /control/stop → 자동매매 정지
    - POST /control/emergency-exit → 전체 Futures 포지션 즉시 청ìT /control/set-leverage → 레버리지 변경
    - WebSocket /ws/status → 실시간 상태 스트림

5-3. monitor/telegram_bot.py:
    - 환경 태그를 USE_TESTNET 값에 따라 자동 결정:
        True  → [TESTNET]
        False → [🔴 MAINNET]
    - 거래 실행 시: "{환경태그}[LONG 3x] BTC/USDT @ 65,000 | Size: 0.01 BTC | Signal Z: 2.1 | Liq: 58,200"
    - 포지션 청산 시: "{환경태그}[CLOSE LONG] BTC/USDT | PnL: +3.6% (lev) | Funding: -$1.20 | Hold: 3h"
    - 일일 리í Aegis Daily | PnL: +2.3% | Trades: 5 | Win: 60% | DD: 1.2% | Funding: -$5.40"
    - 경고 알림: "{환경태그} ⚠️ Drawdown 5% | ⚠️ Liquidation 접근 80%"
    - 긴급 알림: "{환경태그} 🚨 Aegis emergency exit — All Futures positions closed"
    - Mainnet 시작/종료:
        "[🔴 MAINNET] Aegis Futures 시스템 시작됨 — 실제 자산 거래 활성 | Leverage: 3x"
        "[🔴 MAINNET] Aegis 시스템 종료됨"

5-4. analytics/pnl_calculator.py — 수익률 계산 ì - 거래별(per-trade) PnL 계산:
        gross_pnl = (exit_price - entry_price) × size × leverage × direction
        funding_cost = 포지션 보유 중 발생한 펀딩레이트 비용 합산
        trading_fee = entry_fee + exit_fee
        net_pnl = gross_pnl - funding_cost - trading_fee
        net_pnl_pct = net_pnl / (entry_price × size / leverage)  # 마진 대비 수익률
    - 일간/주간/월간 PnL 집계
    - 누적 수익률 곡선 (equity curve) 생성
    - 벤치마크 대비 수익률: BTC Buy&Hold 대비 초과수익(alpha) 계산

5-5. analytics/performance_metrics.py — 성과 지표:
    - Sharpe Ratio (연환산, 위험조정수익률)
    - Sortino Ratio (하방 변동성만 반영)
    - Calmar Ratio (연환산수익률 / 최대 드로다운)
    - 승률 (Win Rate), 손익비 (Profit Factor)
    - 평균 보유 시간, 평균 이익/손실 크기
    - 기대수익 = 승률 × 평균이익 - 패률 × 평균손실
    - 최대 연속 승/패 횟수
    - 시간대별 수ì시 히트맵)
    - 요일별 수익률 분포

5-6. analytics/attribution.py — PnL 귀인 분석:
    - 모델별 기여도: 앙상블에서 각 모델(LightGBM, TRA, ADARNN)이 최종 시그널에 기여한 비율 추적
    - 레짐별 성과: TRENDING / RANGING / VOLATILE 레짐별로 수익률, 승률, 거래 횟수 분리
    - 방향별 성과: 롱 거래 vs 숏 거래 수익률 비교
    - 시간대별 성과: 어느 시간대에 수익이 나고, 어느 시간대에 손실이 나는지
    - PnL에서 펀딩비용이 차지하는 비율
    - 슬리피지 영향: 의도 가격 vs 체결가 차이가 PnL에 미치는 영향 누적

5-7. analytics/report_generator.py — 자동 리포트:
    - 일간 리포트: 당일 거래 요약, PnL, 리스크 현황
    - 주간 리포트: 주간 성과, 모델별 IC 추이, 레짐 분포, 개선 제안
    - 월간 리포트: 월간 성과, BTC 벤치마크 대비, 펀딩비용 분석, 모델 리트레이닝 효과
    - PDF 또는 Markdown 파일로 자ëam 전송 가능

5-8. backoffice/app.py — Streamlit 백오피스 대시보드:
    ⚠️ 이 시스템의 유지관리를 위한 핵심 도구. Streamlit 멀티 페이지 앱으로 구성한다.
    Streamlit은 Python 네이티브라 별도 프론트엔드 빌드가 불필요하고,
    pandas/plotly와 자연스럽게 통합되어 퀀트 대시보드에 최적이다.

    FastAPI 백엔드의 API를 호출하여 데이터를 가져온다.
    streamlit run backoffice/app.py --server.port 8501 --serveh /aegis

    [Page 1: 실시간 운영 대시보드 — 01_live_dashboard.py]
    시스템의 현재 상태를 한눈에 파악하는 메인 화면.
    - 시스템 상태 표시: 🟢 Running / 🟡 Warning / 🔴 Stopped + 환경(TESTNET/MAINNET)
    - 현재 Futures 포지션 카드: side, size, leverage, entry, mark_price, liq_price, unrealized_pnl
    - 청산가격까지 거리 게이지 바 (시각적 경고)
    - 오늘의 PnL 요약: 실현 PnL, 미실현 PnL, 펀딩비용, 순 PnL
    - 최근 quity curve (Plotly 라인 차트)
    - 다음 펀딩레이트 카운트다운 + 예상 비용
    - 최근 5건 거래 이력 + 최근 5건 의사결정 로그 미리보기
    - 긴급 청산 버튼 (확인 다이얼로그 포함)

    [Page 2: 의사결정 감사 추적 — 02_decision_log.py]
    "왜 이 거래를 했는지/안 했는지"를 추적하는 핵심 디버깅 도구.
    - 날짜/시간 범위 필터 + 결정 유형 필터 (EXECUTE/SKIP/REJECTED)
    - DecisionRecord 테이블: timestamp, cision, direction, z_score, regime, reason
    - 행 클릭 시 상세 펼침:
        - 모델별 예측값 비교 막대 차트
        - TRA 라우터 가중치 파이 차트 (어떤 predictor가 활성이었는지)
        - 상위 10개 피처 + 값 테이블
        - 리스크 체크 상세 (어떤 항목을 통과/실패했는지)
        - 체결 결과 (슬리피지, 레이턴시)
    - "이 시점에 다른 결정을 했으면?" 시뮬레이션:
        시그널 threshold를 조정했을 때 결뀌었을지 표시
    - 연속 SKIP 구간 하이라이트 (시그널이 왜 안 나왔는지 패턴 파악)

    [Page 3: 거래 일지 — 03_trade_journal.py]
    모든 거래를 개별적으로 분석하는 도구.
    - 전체 거래 이력 테이블: 진입/청산 시각, 방향, 크기, 진입가, 청산가, 보유시간, gross/net PnL
    - 개별 거래 클릭 시 상세:
        - 진입~청산 구간 캔들 차트 + 진입/청산 포인트 마커
        - 해당 거래의 DecisionRecord (왜 했는지)
        - 청산 이유 (SL/TP/시그널 반전/수동 청산/긴급 청산)
        - 보유 중 경험한 최대 이익(MFE)과 최대 손실(MAE)
    - 필터: 날짜 범위, 방향(롱/숏), 결과(이익/손실), 레짐
    - 거래 메모 추가 기능: 수동으로 메모를 달아서 나중에 복기 가능

    [Page 4: 수익률 분석 — 04_pnl_analytics.py]
    수익률을 다각도로 분석하는 대시보드.
    - 누적 수익률 곡선 (equity curve) — BTC Buy&Hold 벤치마로다운 차트 (underwater chart)
    - 일간/주간/월간 PnL 히트맵 (달력 형태)
    - 수익률 분포 히스토그램 (정규분포 피팅)
    - 핵심 지표 카드: Sharpe, Sortino, Calmar, 승률, 손익비, 기대수익
    - PnL 귀인 분석 탭:
        - 모델별 기여도 stacked bar chart
        - 레짐별 수익률 비교 bar chart
        - 롱 vs 숏 수익률 비교
        - 시간대별 수익률 히트맵
        - 펀딩비용 누적 차트
        - 슬리피지 누적 ì기간 비교: 이번 주 vs 지난 주, 이번 달 vs 지난 달 성과 비교

    [Page 5: 모델 모니터링 — 05_model_monitor.py]
    모델이 여전히 잘 작동하는지 감시하는 도구. 모델 성능 저하를 조기 감지한다.
    - IC(Information Coefficient) 추이 차트: 모델별 rolling IC (7일, 30일 윈도우)
    - Rank IC 추이 차트
    - 모델별 방향 정확도 (맞은 방향 비율) 추이
    - 앙상블 vs 개별 모델 성과 비교 (앙상블이 정말 더 나ì예측값 분포 변화 감지:
        최근 7일 예측값 분포 vs 학습 기간 분포 비교 (KL-Divergence)
        분포가 크게 달라지면 ⚠️ 경고 (모델 스탈 가능성)
    - 피처 중요도 변화: 리트레이닝 전후 피처 중요도 변화 비교
    - TRA 라우터 활성 빈도: 어떤 predictor가 얼마나 자주 선택되었는지 시계열
    - 마지막 리트레이닝 시각 + 다음 리트레이닝 예정 시각
    - 모델 스탈 경고: IC가 N일 연속 0 이í¶장 알림

    [Page 6: 리스크 대시보드 — 06_risk_dashboard.py]
    현재 리스크 노출을 한눈에 파악하는 도구.
    - 계좌 잔고 추이 + 전고점(HWM) 오버레이
    - 현재 드로다운 게이지 (0% ~ 10% 시각화, 5%/8%/10% 임계선 표시)
    - 레버리지 사용률: 현재 사용 중인 실효 레버리지 vs 최대 허용
    - 일일 손실 한도 사용률: 오늘 사용한 손실 예산 vs 남은 예산
    - 일일 거래 횟수: 오늘 실행한 거래 vs ì°속 손실 카운터: 현재 연속 손실 횟수 (5회 쿨다운 기준)
    - 리스크 이벤트 타임라인: 언제 리스크 시스템이 개입했는지 시계열
        (포지션 축소, 거래 차단, 쿨다운, 긴급 청산 등 이벤트)
    - 청산가격 거리 히스토리: 청산가격에 가장 가까웠던 순간들 목록

    [Page 7: 백테스트 결과 뷰어 — 07_backtest_viewer.py]
    과거 백테스트 결과를 비교 분석하는 도구.
    - 저장된 백테스트 결êª©록 (날짜, 파라미터, 성과 지표)
    - 백테스트 선택 시 상세:
        - Equity curve, 드로다운 차트
        - 거래 목록 + 통계
        - 파라미터 설정값
    - 백테스트 간 비교: 2개 이상 선택하여 equity curve 오버레이, 지표 비교 테이블
    - "라이브 vs 백테스트" 비교: 실제 라이브 성과와 동일 기간 백테스트 성과 비교
        (괴리가 크면 백테스트 모델에 문제가 있다는 의미)

    [Page 8: 시스템 stem_ops.py]
    시스템 건강 상태와 디버깅을 위한 도구.
    - 실시간 로그 뷰어: 로그 레벨 필터 (DEBUG/INFO/WARNING/ERROR/CRITICAL)
    - 에러 트래커: 최근 에러 목록, 발생 빈도, 마지막 발생 시각
    - 파이프라인 레이턴시 모니터:
        캔들 수신 → 피처 계산 → 모델 추론 → 시그널 → 리스크 → 주문 실행
        각 단계별 소요 시간 waterfall 차트
    - API rate limit 사용량: Binance API 호출 현황 + 남ì - WebSocket 연결 상태: 연결/재연결 이력, 마지막 heartbeat 시각
    - 데이터 파이프라인 건강:
        마지막 캔들 수신 시각, 누락된 캔들 수, DB 크기
    - 스케줄러 상태: 다음 실행 예정 작업 목록 + 마지막 실행 결과
    - 설정 뷰어: 현재 활성 설정값 전체 표시 (민감 정보 마스킹)
    - 수동 제어:
        - 시스템 시작/중지 버튼
        - 긴급 청산 버튼 (이중 확인)
        - 강제 리트레이닝 트- 레버리지 변경 슬라이더

5-9. Docker Compose 구성:
    services:
      aegis-trader:     # 메인 트레이딩 봇
      aegis-api:        # FastAPI 백엔드 (port 8000)
      aegis-backoffice: # Streamlit 백오피스 (port 8501)
    볼륨: ./data/db 마운트 (데이터 영속성)
    네트워크: aegis-backoffice → aegis-api 내부 통신
```

### 검증 기준 (Phase 5 완료 조건)

```
✅ orchestrator가 30분 간격으로 전체 파이프라인 자동 실행
✅ 새 캔들 → 피 포함) → 모델 추론 → 시그널 → 리스크체크 → Futures 주문 흐름 E2E 동작
✅ decision_logger가 매 캔들마다 DecisionRecord를 DB에 기록
✅ FastAPI 서버 기동, /health 200 OK
✅ /positions API가 Futures 포지션 상세(side, leverage, liquidation_price) 반환
✅ /decisions API가 DecisionRecord 조회 가능
✅ pnl_calculator가 레버리지 + 펀딩비용 + 수수료 반영한 정확한 PnL 산출
✅ performance_metrics가 Sharpe, Sortino, Calmar, 승률 등 정í attribution 분석이 모델별/레짐별/방향별 PnL 분리 가능
✅ Streamlit 백오피스 기동 (port 8501), 8개 페이지 모두 접근 가능:
   - 실시간 대시보드에서 현재 포지션 + equity curve 표시
   - 의사결정 뷰어에서 개별 DecisionRecord 상세 조회 가능
   - 거래 일지에서 개별 거래의 캔들 차트 + 진입/청산 마커 표시
   - 수익률 분석에서 equity curve + BTC 벤치마크 오버레이
   - 모델 모니터에서 IC 추이 + 피처 ì - 리스크 대시보드에서 드로다운 게이지 + 이벤트 타임라인
   - 시스템 운영에서 로그 뷰어 + 레이턴시 waterfall 작동
✅ /control/emergency-exit 호출 시 Testnet에서 전 Futures 포지션 청산 확인
✅ Telegram 알림 전송 확인
✅ Docker Compose up으로 전체 시스템(aegis-trader + aegis-api + aegis-backoffice) 기동 성공
✅ pytest test_e2e_pipeline.py PASS
```

---

## Phase 6: E2E 통합 테스트 + Futures Testnet 실거래 최종 검증

### ënce Futures Testnet에서 최소 24시간 운영하고, 롱/숏 양방향 거래 사이클을 완전히 검증한다.
⚠️ 이 Phase의 모든 테스트와 운영은 Futures Testnet에서만 수행한다. Mainnet 전환은 자동화 범위 밖이다.

### 상세 작업

```
6-1. E2E 통합 테스트 시나리오:
    ⚠️ 모든 시나리오는 USE_TESTNET=True 상태에서 Binance Futures Testnet으로 실행한다.

    시나리오 A — Futures 정상 거래 사이클:
        1. 시스템 시작 (NET=True)
        2. Futures 초기 설정 확인 (leverage, margin_type)
        3. Binance Vision 히스토리컬 Futures 데이터 로드 + 모델 로드
        4. 실시간 Futures WebSocket 데이터 수신 대기
        5. 롱 시그널 발생 → Futures Testnet에서 롱 진입 → 포지션 확인 (side, leverage, liq_price)
        6. 스탑로스 또는 테이크프로핏 도달 → 자동 청산
        7. 숏 시그널 발생 → 숏 진입 → 포지션 확인 → 청산
        8. 거래 ì PnL 기록 확인 (레버리지 반영 PnL, 펀딩 비용 포함)
        9. 모든 로그에 [TESTNET] 태그 포함 확인

    시나리오 B — 리스크 시스템 검증:
        1. 의도적으로 큰 포지션 시그널 생성 → 포지션 한도에서 차단 확인
        2. 의도적으로 연속 손실 발생 → 쿨다운 활성화 확인
        3. drawdown 임계치 도달 → 전체 Futures 포지션 청산 + 시스템 정지 확인
        4. 청산가격 접근 시뮬레이션 → 80% ì¸

    시나리오 C — 장애 복구:
        1. Futures WebSocket 연결 끊기 → 자동 재연결 확인
        2. API 서버 재시작 → Futures 포지션 상태 복구 확인
        3. 미체결 주문 존재 시 → 시스템 재시작 후 정리 확인

    시나리오 D — Mainnet 전환 대비 아키텍처 검증:
        ⚠️ 이 시나리오는 실제 Mainnet 거래를 하지 않는다.
        .env에서 USE_TESTNET=False로 변경했을 때 아키텍처가 올바르게 분기되ë 벨에서 검증하는 테스트이다.

        tests/test_mainnet_readiness.py:

        1. 설정 분기 테스트:
            - USE_TESTNET=True일 때 settings가 Testnet API 키를 반환하는지 확인
            - USE_TESTNET=False일 때 settings가 Mainnet API 키를 반환하는지 확인
            - 두 환경에서 다른 키 쌍이 로드되는지 assert

        2. Executor 초기화 분기 테스트 (실제 API 호출 없이 mock):
            - USE_TESTNET=True  → CCXT sandbox=Tru기화되는지 확인
            - USE_TESTNET=False → CCXT sandbox=False로 초기화되는지 확인
            - 양쪽 모두 defaultType='future'로 초기화되는지 확인
            - USE_TESTNET=False일 때 Mainnet safety guard가 활성화되는지 확인:
                - 경고 로그 3회 출력 확인
                - 첫 주문 전 5초 대기 로직 존재 확인
                - 단일 주문 최대 금액이 5%로 축소되는지 확인
                - 일일 최대 거래 횟확인
            - Futures 초기 설정(leverage, marginType)이 양쪽 환경에서 동일하게 적용되는지 확인

        3. 로그 태그 분기 테스트:
            - USE_TESTNET=True  → [TESTNET] 태그 포함 확인
            - USE_TESTNET=False → [MAINNET] 태그 포함 확인

        4. Telegram 알림 분기 테스트 (mock):
            - USE_TESTNET=True  → "[TESTNET]" 프리픽스 확인
            - USE_TESTNET=False → "[🔴 MAINNET]" 프리픽스 확인
            - Ma 별도 경고 알림 발송 확인

        5. 리스크 엔진 분기 테스트:
            - USE_TESTNET=False일 때 리스크 파라미터가 더 보수적으로 적용되는지 확인
            - Mainnet에서의 emergency-exit 로직이 정상 동작하는지 확인 (mock)

        6. Paper Trader 인터페이스 호환 테스트:
            - paper_trader와 binance_executor가 동일한 인터페이스(ABC) 구현 확인
            - 전략 레이어에서 executor를 교체해도 코드 변ê동작하는지 확인

        7. 전체 의존성 그래프 검증:
            - 모든 컴포넌트가 USE_TESTNET 값을 settings에서만 읽는지 확인
            - 하드코딩된 sandbox=True/False가 존재하지 않는지 코드 스캔
            - executor 외부에서 직접 CCXT 인스턴스를 생성하는 코드가 없는지 확인

6-2. 성능 벤치마크:
    - 시그널 생성 레이턴시: 캔들 수신 → 주문 실행까지 < 5초
    - 메모리 사용량: < 2GB (24시간 연ì파일 크기 관리: 일별 로테이션

6-3. Mainnet 전환 체크리스트 (README.md에 문서로 포함):
    ⚠️ Mainnet 전환은 사용자가 수동으로 판단하고 진행하는 영역이다.
    ⚠️ 아래 체크리스트를 모두 통과한 후에만 USE_TESTNET=False로 변경한다.

    - [ ] Futures Testnet에서 최소 48시간 안정 운영 확인
    - [ ] 롱/숏 양방향 거래 모두 정상 체결 확인
    - [ ] 청산가격 접근 경고 시스템 작동 확인
    - [ ] í°이 정확히 기록되는지 확인
    - [ ] 0건의 미처리 에러 확인
    - [ ] risk_engine이 모든 시나리오에서 정상 작동 확인
    - [ ] test_mainnet_readiness.py 전체 PASS 확인
    - [ ] .env에서 USE_TESTNET=False로 변경 (이것만으로 Mainnet 전환 완료)
    - [ ] .env에 CT_BINANCE_API_KEY, CT_BINANCE_API_SECRET가 유효한 Mainnet Futures 키인지 확인
    - [ ] Mainnet API 키에 **Enable Futures** 권한이 활성화되어 있는지 확인
    - [ ] Mainnetle Withdrawals는 비활성** 상태인지 확인
    - [ ] 초기 자본을 소액 (50-100 USDT)으로 설정
    - [ ] 레버리지를 보수적으로 설정 (1~2x로 시작)
    - [ ] emergency-exit API 접근 가능 확인
    - [ ] Telegram에 "[🔴 MAINNET] Aegis Futures 시스템 시작됨" 알림 수신 확인
```

### 최종 검증 기준 (전체 프로젝트 완료 조건)

```
✅ Binance Vision에서 Futures 히스토리컬 데이터 다운로드 + 무결성 검증 통과
✅ Binance Futures Te 사이클 실행 및 체결 확인:
   - 롱 진입 → 포지션 확인(leverage, liq_price) → 청산
   - 숏 진입 → 포지션 확인 → 청산
   - 시그널 기반 자동 롱/숏 전환
✅ 의사결정 감사 추적(Audit Trail) 완전 작동:
   - 모든 캔들에 대해 DecisionRecord 기록 (EXECUTE/SKIP/REJECTED 포함)
   - 백오피스 의사결정 뷰어에서 개별 레코드 상세 조회 가능
✅ 백오피스 대시보드(Streamlit) 8개 페이지 전체 작동:
   - 실시간 대ì의사결정 추적, 거래 일지, 수익률 분석,
     모델 모니터링, 리스크 대시보드, 백테스트 뷰어, 시스템 운영
✅ 수익률 분석 엔진 작동:
   - 레버리지/펀딩비용/수수료 반영 PnL 정확 산출
   - PnL 귀인 분석 (모델별, 레짐별, 방향별, 시간대별)
   - Sharpe, Sortino, Calmar 등 성과 지표 계산
   - BTC Buy&Hold 벤치마크 대비 초과수익 계산
✅ 모델 모니터링 작동:
   - IC 추이, 피처 중요도 변화, 예측값 ë
✅ USE_TESTNET=True 상태에서 모든 로그에 [TESTNET] 태그 포함
✅ Mainnet 전환 대비 아키텍처 검증 통과:
   - test_mainnet_readiness.py 전체 PASS
   - USE_TESTNET=False 시 설정/키/sandbox/로그/알림/리스크 파라미터 자동 분기 확인
   - 양쪽 환경 모두 defaultType='future' 유지 확인
   - 하드코딩된 sandbox 값 없음 (settings 단일 소스 확인)
   - executor 인터페이스 통일 (paper_trader ↔ binance_executor 교체 가능)
✅ 전체 pt 테스트 스위트 PASS (unit + integration + e2e + mainnet_readiness)
✅ Docker Compose로 Aegis 원커맨드 시스템 기동 (aegis-trader + aegis-api + aegis-backoffice)
✅ README.md에 Aegis 설치/실행/설정 가이드 + Mainnet Futures 전환 체크리스트 완성
✅ 코드 품질: mypy/ruff 경고 0건
```

---

## 에이전트별 역할 분배 가이드 (OMC Team 모드용)

OMC의 team 모드에서 아래와 같이 에이전트를 분배한다:

```
Agent 1 (Data Engineer):
  담당: Phas1 전체
  파일: data/, config/, scripts/download_binance_vision.py, scripts/backfill_data.py
  기술: Binance Vision API, CCXT Futures WebSocket, pandas, SQLAlchemy
  핵심: 히스토리컬 데이터는 반드시 Binance Vision Futures 경로에서 다운로드

Agent 2 (ML Engineer):
  담당: Phase 2 전체
  파일: models/
  기술: LightGBM, PyTorch, Qlib, scikit-learn
  의존성: Phase 1 완료 후 시작

Agent 3 (Strategy/Risk Engineer):
  담당: Phase 3 전체
  파일: strategy/ (decision_lr.py 포함), risk/
  기술: 퀀트 전략 로직, 리스크 관리, 의사결정 감사 추적
  핵심: decision_logger가 모든 의사결정의 "왜?"를 빠짐없이 기록하도록 설계
  의존성: Phase 2 완료 후 시작 (모델 예측값 필요)

Agent 4 (Execution Engineer):
  담당: Phase 4 전체
  파일: execution/, tests/test_binance_executor.py
  기술: CCXT (defaultType='future'), Binance Futures Testnet API, 주문 관리
  핵심: 모든 거래 코드는 Testnet Only. USE_TESTNET ë처 준수.
  병렬 가능: Phase 1 완료 후 Agent 2, 3과 병렬 진행 가능

Agent 5 (Platform Engineer):
  담당: Phase 5 — 오케스트레이터 + API + Telegram + Docker
  파일: scheduler/, api/, monitor/, docker-compose.yml
  기술: FastAPI, APScheduler, Docker, Telegram Bot
  의존성: Phase 3, 4 완료 후 통합

Agent 6 (Analytics & Backoffice Engineer):
  담당: Phase 5 — 분석 엔진 + 백오피스 대시보드
  파일: analytics/, backoffice/
  기술: Streamlit, Plotly, pan트 성과 분석
  핵심 산출물:
    - pnl_calculator: 레버리지/펀딩비용/수수료 반영 정확한 PnL
    - performance_metrics: Sharpe, Sortino, Calmar 등
    - attribution: 모델별/레짐별/방향별 PnL 귀인 분석
    - Streamlit 8개 페이지 백오피스 대시보드
  의존성: Agent 3의 decision_logger + Agent 5의 API 완료 후 시작
  병렬 가능: analytics/ 엔진은 Phase 3 완료 시점부터 병렬 개발 가능

통합 테스트 (Phase 6):
  모든 Agent가 협력ís Testnet E2E 검증 수행
```

---

## 안전 수칙

```
🔴 절대 금지 — 이 규칙은 어떤 상황에서도 예외 없이 적용된다:
- 개발/테스트 과정에서 USE_TESTNET=False로 변경하여 Mainnet 거래를 실행하지 않는다.
- 모든 백테스팅, 통합 테스트, E2E 테스트, 주문 실행 테스트는 USE_TESTNET=True 상태에서만 수행한다.
- Mainnet API 키(CT_BINANCE_API_KEY)를 테스트 코드에서 직접 호출하지 않는다.
  test_mainnet_readiness.pyëk으로만 검증한다.
- .env 파일을 git에 커밋하지 않는다.
- 히스토리컬 데이터를 CCXT fetch_ohlcv()로 대량 수집하지 않는다.
  과거 데이터는 반드시 Binance Vision(https://data.binance.vision)에서 다운로드한다.
- USE_TESTNET 값을 settings.py 이외의 곳에서 하드코딩하지 않는다.
  모든 컴포넌트는 settings로부터 환경 정보를 주입받아야 한다.

🟢 아키텍처 원칙:
- USE_TESTNET 단일 토글로 Testnet ↔ Mainnet 전체 야 한다.
  코드 수정 없이 .env의 USE_TESTNET 값만 바꾸면 환경이 전환되는 구조.
- 모든 환경 의존 분기(API 키, sandbox, 로그 태그, 리스크 파라미터)는 settings.py에서
  USE_TESTNET 값에 따라 결정되고, 각 컴포넌트에 주입된다.
- Executor는 ABC 인터페이스로 추상화하여 paper_trader/binance_executor를 전략 변경 없이 교체 가능.

🟢 데이터 소스 원칙:
- 히스토리컬/백테스트 데이터 → Binance Vision (https://datvision)
- 실시간 라이브 데이터 → CCXT WebSocket / Binance WebSocket
- Binance Vision과 실시간 데이터 사이의 갭 → CCXT fetch_ohlcv로 최소한만 채움
- 모든 다운로드 데이터는 SHA256 체크섬으로 무결성 검증

🟡 주의:
- 모든 금액은 USDT 기준으로 통일한다
- Testnet 잔고가 부족하면 Binance Testnet Faucet에서 충전한다
- rate limit 초과 시 즉시 백오프, 절대 무한 재시도하지 않는다
- 모든 주문에는 고유 client_ordd를 부여하여 추적 가능하게 한다
- 로그에는 반드시 환경 태그([TESTNET] 또는 [MAINNET])를 포함한다
```
