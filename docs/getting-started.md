# 시작하기

## 프로젝트 개요

Aegis는 Binance Futures 테스트넷에서 BTC/USDT 선물거래를 자동으로 운영하는 AI 기반 암호화폐 자동 거래 시스템입니다. 머신러닝 모델(LightGBM, TRA, ADARNN 앙상블)을 사용하여 거래 신호를 생성하고, 리스크 관리 및 자동 실행을 수행합니다.

## 필수 요구사항

- **Python 3.10 이상**
- **uv 패키지 매니저** ([설치](https://github.com/astral-sh/uv))
- **Binance Futures 테스트넷 API 키**
  - 테스트넷 등록: https://testnet.binancefuture.com
  - API 키 생성: 계정 설정 > API Management에서 API 키 생성
  - 필요한 권한: Futures 거래 권한 활성화

## 빠른 시작

### 1단계: 클론 및 설치

```bash
git clone https://github.com/riemannulus/aegis.git
cd aegis
uv sync
```

### 2단계: 환경 변수 설정

`.env.example`을 복사하여 `.env` 파일을 생성합니다:

```bash
cp .env.example .env
```

`.env` 파일을 편집하여 다음을 설정합니다:

```env
# Binance Futures 테스트넷 API 키
CT_BINANCE_TESTNET_API_KEY=your_testnet_api_key_here
CT_BINANCE_TESTNET_API_SECRET=your_testnet_api_secret_here

# 거래 설정
USE_TESTNET=True
TRADING_SYMBOL=BTC/USDT:USDT
TIMEFRAME=30m
```

### 3단계: 과거 데이터 다운로드

```bash
uv run python scripts/download_binance_vision.py --symbol BTCUSDT --interval 30m --start 2024-01-01 --end 2025-01-01
```

이 명령은 Binance Vision에서 2024-01-01부터 2025-01-01까지의 30분 간격 OHLCV 데이터를 다운로드합니다.

### 4단계: 모델 훈련

```bash
uv run python scripts/train_models.py
```

이 명령은 다음 모델들을 훈련하고 저장합니다:
- **LightGBM**: 경량 그래디언트 부스팅 모델
- **TRA**: 거래 체계 기반 앙상블 모델
- **ADARNN**: 적응형 RNN 기반 모델

### 5단계: 백테스트 실행

```bash
uv run python scripts/run_backtest.py
```

훈련된 모델을 사용하여 과거 데이터에 대한 백테스트를 실행합니다. 결과는 `data/backtest_results/` 디렉터리에 저장됩니다.

### 6단계: API 서버 시작

```bash
uv run uvicorn api.main:app --port 8000
```

FastAPI 기반 REST API 서버가 http://localhost:8000에서 시작됩니다.
- 전체 API 문서: http://localhost:8000/docs
- OpenAPI 스키마: http://localhost:8000/openapi.json

### 7단계: 백오피스 대시보드 시작

```bash
uv run streamlit run backoffice/app.py --server.port 8501
```

Streamlit 기반 실시간 모니터링 대시보드가 http://localhost:8501에서 시작됩니다.

### 8단계: Docker로 실행 (선택사항)

모든 서비스를 Docker Compose로 함께 실행합니다:

```bash
docker compose up
```

서비스 구성:
- **aegis-trader**: 거래 실행 엔진 (백그라운드)
- **aegis-api**: REST API 서버 (포트 8000)
- **aegis-backoffice**: Streamlit 대시보드 (포트 8501)

## 주요 디렉터리 구조

```
aegis/
├── api/                    # FastAPI 엔드포인트
│   ├── main.py
│   ├── routes/            # 개별 라우트 모듈
│   └── websocket.py
├── backoffice/            # Streamlit 대시보드
│   ├── app.py
│   ├── pages/             # 8개 페이지
│   ├── components/
│   └── api_client.py
├── data/                  # 데이터 저장소 및 특성 공학
│   ├── storage.py
│   └── feature_engineer.py
├── models/                # 모델 정의 및 훈련
│   ├── trainer.py
│   └── saved/             # 훈련된 모델 저장소
├── strategy/              # 거래 신호 및 위치 관리
├── risk/                  # 리스크 관리
├── execution/             # 주문 실행
├── scheduler/             # 작업 스케줄러
├── scripts/               # 유틸리티 스크립트
│   ├── download_binance_vision.py
│   ├── train_models.py
│   ├── run_backtest.py
│   └── backfill_data.py
├── tests/                 # 유닛 및 통합 테스트
├── .env.example
├── pyproject.toml
└── docker-compose.yml
```

## 다음 단계

- **API 문서**: `docs/api-reference.md`를 참조하여 REST API 엔드포인트 사용법을 학습합니다.
- **백오피스 가이드**: `docs/backoffice-guide.md`를 참조하여 대시보드의 각 페이지 기능을 이해합니다.
- **시스템 아키텍처**: `docs/architecture.md`를 참조하여 내부 설계 및 데이터 흐름을 학습합니다.

## 문제 해결

### 모델 로드 실패
- `models/saved/` 디렉터리가 존재하고 모델 파일이 있는지 확인합니다.
- `uv run python scripts/train_models.py`를 다시 실행합니다.

### 데이터베이스 오류
- `data/aegis.db` 파일의 권한을 확인합니다.
- 파일을 삭제하고 다시 실행합니다 (처음부터 시작하는 경우).

### API 포트 이미 사용 중
- 다른 포트로 실행: `uv run uvicorn api.main:app --port 8001`
- 또는 기존 프로세스를 종료합니다: `lsof -ti:8000 | xargs kill -9`

### Streamlit 연결 오류
- `.env`의 `AEGIS_API_URL`이 올바른지 확인합니다 (기본값: http://localhost:8000).
- API 서버가 실행 중인지 확인합니다.
