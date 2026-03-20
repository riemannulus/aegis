# API 레퍼런스

Aegis API는 FastAPI 기반 REST API입니다. 모든 엔드포인트는 `http://localhost:8000` (또는 배포된 호스트)에서 접근 가능합니다.

API 대화형 문서: http://localhost:8000/docs

## 기본 정보

- **기본 URL**: `http://localhost:8000`
- **응답 형식**: JSON
- **CORS**: 모든 출처 허용

## 헬스 체크

### GET /health/

시스템 상태 및 준비 상황을 확인합니다.

**응답 스키마:**

```json
{
  "status": "running",
  "testnet": true,
  "environment": "TESTNET",
  "version": "0.1.0",
  "models_loaded": true,
  "last_signal_at": "2025-03-19T12:34:56.789Z",
  "uptime": "5h 23m 14s",
  "db_size_mb": 45.67
}
```

**예제:**

```bash
curl http://localhost:8000/health/
```

---

## 포지션 (Positions)

### GET /positions/

현재 활성 포지션을 반환합니다.

**응답 스키마:**

```json
{
  "side": "long",
  "size": 0.05,
  "leverage": 1,
  "entry_price": 42500.0,
  "mark_price": 43200.0,
  "liquidation_price": 35000.0,
  "unrealized_pnl": 350.0
}
```

**예제:**

```bash
curl http://localhost:8000/positions/
```

### GET /positions/current

최근 포지션 히스토리를 반환합니다.

**쿼리 파라미터:**

| 파라미터 | 타입 | 기본값 | 설명 |
|---------|------|--------|------|
| `limit` | int | 5 | 반환할 레코드 수 |

**응답 스키마:**

```json
[
  {
    "timestamp": 1710866096000,
    "side": "long",
    "entry_price": 42500.0,
    "size": 0.05,
    "unrealized_pnl": 350.0,
    "liquidation_price": 35000.0
  }
]
```

**예제:**

```bash
curl "http://localhost:8000/positions/current?limit=10"
```

---

## 거래 (Trades)

### GET /trades/

거래 이력을 반환합니다.

**쿼리 파라미터:**

| 파라미터 | 타입 | 기본값 | 설명 |
|---------|------|--------|------|
| `limit` | int | 500 | 반환할 레코드 수 |

**응답 스키마:**

```json
[
  {
    "timestamp": 1710866096000,
    "side": "long",
    "size": 0.05,
    "entry_price": 42500.0,
    "exit_price": 43200.0,
    "pnl": 35.0,
    "pnl_pct": 0.082,
    "funding_cost": 0.5,
    "duration_ms": 3600000
  }
]
```

**예제:**

```bash
curl "http://localhost:8000/trades/?limit=100"
```

---

## 펀딩 수수료 (Funding)

### GET /funding-history/

펀딩 수수료 히스토리를 반환합니다.

**쿼리 파라미터:**

| 파라미터 | 타입 | 기본값 | 설명 |
|---------|------|--------|------|
| `limit` | int | 50 | 반환할 레코드 수 |

**응답 스키마:**

```json
[
  {
    "timestamp": 1710866096000,
    "symbol": "BTCUSDT",
    "funding_rate": 0.0001,
    "funding_amount": 2.5
  }
]
```

**예제:**

```bash
curl "http://localhost:8000/funding-history/?limit=100"
```

---

## 신호 (Signals)

### GET /signals/latest

최신 모델 신호를 반환합니다.

**쿼리 파라미터:**

| 파라미터 | 타입 | 기본값 | 최대값 | 설명 |
|---------|------|--------|--------|------|
| `limit` | int | 10 | 100 | 반환할 신호 수 |

**응답 스키마:**

```json
[
  {
    "timestamp": 1710866096000,
    "model_name": "lgbm",
    "prediction": 0.65,
    "position_signal": 0.5
  },
  {
    "timestamp": 1710866096000,
    "model_name": "tra",
    "prediction": 0.72,
    "position_signal": 0.6
  }
]
```

**예제:**

```bash
curl "http://localhost:8000/signals/latest?limit=20"
```

---

## 의사결정 로그 (Decisions)

### GET /decisions/

모든 거래 의사결정 기록을 반환합니다 (EXECUTE/SKIP/REJECTED).

**쿼리 파라미터:**

| 파라미터 | 타입 | 기본값 | 최대값 | 설명 |
|---------|------|--------|--------|------|
| `limit` | int | 50 | 500 | 반환할 레코드 수 |

**응답 스키마:**

```json
[
  {
    "timestamp": 1710866096000,
    "decision": "EXECUTE",
    "direction": "long",
    "z_score": 2.34,
    "regime": "trending_up",
    "reason": "Strong ensemble signal with low drawdown",
    "full_record": {}
  }
]
```

**예제:**

```bash
curl "http://localhost:8000/decisions/?limit=100"
```

---

## 메트릭 (Metrics)

### GET /metrics/

당일 거래 메트릭을 반환합니다.

**응답 스키마:**

```json
{
  "today_realized_pnl": 125.50,
  "today_funding_cost": 5.25,
  "unrealized_pnl": 350.0,
  "total_trades_today": 12,
  "account_balance": 0.0
}
```

**예제:**

```bash
curl http://localhost:8000/metrics/
```

---

## 분석 (Analytics)

### GET /analytics/pnl-summary

손익 요약 통계를 반환합니다.

**응답 스키마:**

```json
{
  "total_trades": 145,
  "win_rate": 0.58,
  "total_pnl": 3250.75,
  "sharpe": 1.45,
  "max_drawdown": 0.12
}
```

**예제:**

```bash
curl http://localhost:8000/analytics/pnl-summary
```

### GET /analytics/equity-curve

자산 곡선 데이터를 반환합니다.

**응답 스키마:**

```json
[
  {
    "timestamp": 1710866096000,
    "equity": 10000.0
  },
  {
    "timestamp": 1710866400000,
    "equity": 10125.50
  }
]
```

**예제:**

```bash
curl http://localhost:8000/analytics/equity-curve
```

### GET /analytics/performance

상세 성과 지표를 반환합니다.

**응답 스키마:**

```json
{
  "total_trades": 145,
  "win_rate": 0.58,
  "total_pnl": 3250.75,
  "sharpe": 1.45,
  "sortino": 1.82,
  "calmar": 1.56,
  "max_drawdown": 0.12,
  "avg_trade_pnl": 22.42,
  "best_trade": 250.0,
  "worst_trade": -85.5
}
```

**성과 지표 설명:**
- **Sharpe Ratio**: 초과 수익 대비 변동성 비율 (높을수록 좋음)
- **Sortino Ratio**: 음수 변동성만 고려한 Sharpe (높을수록 좋음)
- **Calmar Ratio**: 총 수익 대비 최대 낙폭 비율 (높을수록 좋음)
- **Max Drawdown**: 최고점에서 최저점까지의 하락률 (낮을수록 좋음)

**예제:**

```bash
curl http://localhost:8000/analytics/performance
```

### GET /analytics/attribution

손익 기여도 분석을 반환합니다.

**응답 스키마:**

```json
{
  "by_model": {
    "lgbm": 1200.0,
    "tra": 800.0,
    "adarnn": 1250.75
  },
  "by_regime": {
    "trending_up": 2100.0,
    "ranging": 1150.75
  },
  "by_hour": {
    "00": 145.5,
    "01": 256.3
  }
}
```

**예제:**

```bash
curl http://localhost:8000/analytics/attribution
```

---

## 모델 (Models)

### GET /models/metrics

모델 성과 지표를 반환합니다.

**응답 스키마:**

```json
{
  "last_retrain_at": "2025-03-19T10:30:00",
  "next_retrain_at": null,
  "ic_history": [],
  "rank_ic_history": [],
  "direction_accuracy": null,
  "feature_importance": {
    "rsi": 0.15,
    "macd": 0.12,
    "bb_width": 0.08
  },
  "prediction_distribution_drift": null,
  "tra_router_activity": {},
  "ensemble_vs_individual": {},
  "model_files": ["lgbm.pkl", "tra.pkl", "adarnn.pt"]
}
```

**예제:**

```bash
curl http://localhost:8000/models/metrics
```

---

## 리스크 (Risk)

### GET /risk/status

현재 리스크 상태를 반환합니다.

**응답 스키마:**

```json
{
  "drawdown_pct": 0.12,
  "daily_loss_pct": 0.08,
  "position_ratio": 0.5,
  "consecutive_losses": 2,
  "risk_level": "medium"
}
```

**리스크 레벨:**
- **low**: 최대 낙폭 < 7%, 연속 손실 < 3
- **medium**: 최대 낙폭 7-15%, 연속 손실 3-4
- **high**: 최대 낙폭 > 15%, 연속 손실 >= 5

**예제:**

```bash
curl http://localhost:8000/risk/status
```

### GET /risk/events

리스크 이벤트 히스토리를 반환합니다.

**쿼리 파라미터:**

| 파라미터 | 타입 | 기본값 | 설명 |
|---------|------|--------|------|
| `limit` | int | 100 | 반환할 레코드 수 |

**응답 스키마:**

```json
[]
```

**예제:**

```bash
curl "http://localhost:8000/risk/events?limit=50"
```

---

## 백테스트 (Backtests)

### GET /backtests/

백테스트 결과 목록을 반환합니다.

**응답 스키마:**

```json
[
  {
    "id": "backtest_20250319_100000"
  },
  {
    "id": "backtest_20250318_150000"
  }
]
```

**예제:**

```bash
curl http://localhost:8000/backtests/
```

### GET /backtests/{backtest_id}

특정 백테스트 상세 결과를 반환합니다.

**경로 파라미터:**

| 파라미터 | 타입 | 설명 |
|---------|------|------|
| `backtest_id` | str | 백테스트 ID |

**응답 스키마:**

```json
{
  "id": "backtest_20250319_100000",
  "symbol": "BTCUSDT",
  "start_date": "2024-01-01",
  "end_date": "2025-01-01",
  "timeframe": "30m",
  "total_trades": 145,
  "win_rate": 0.58,
  "total_pnl": 3250.75,
  "sharpe": 1.45,
  "max_drawdown": 0.12,
  "trades": []
}
```

**예제:**

```bash
curl http://localhost:8000/backtests/backtest_20250319_100000
```

### POST /backtests/run

새 백테스트 실행을 시작합니다.

**요청 본문:** 없음 (기본값 사용)

**응답 스키마:**

```json
{
  "success": true,
  "message": "Backtest run triggered (async stub)"
}
```

**예제:**

```bash
curl -X POST http://localhost:8000/backtests/run
```

---

## 시스템 (System)

### GET /system/logs

시스템 로그를 반환합니다.

**쿼리 파라미터:**

| 파라미터 | 타입 | 기본값 | 설명 |
|---------|------|--------|------|
| `level` | str | "INFO" | 로그 레벨 (DEBUG, INFO, WARNING, ERROR) |
| `limit` | int | 200 | 반환할 레코드 수 |

**응답 스키마:**

```json
[
  {
    "timestamp": 1710866096000,
    "level": "INFO",
    "logger": "scheduler.orchestrator",
    "message": "Trading loop iteration started"
  }
]
```

**예제:**

```bash
curl "http://localhost:8000/system/logs?level=INFO&limit=50"
```

### GET /system/scheduler

스케줄러 상태를 반환합니다.

**응답 스키마:**

```json
{
  "running": false,
  "jobs": [],
  "next_run": null
}
```

**예제:**

```bash
curl http://localhost:8000/system/scheduler
```

### GET /system/latency

파이프라인 지연 시간을 반환합니다.

**응답 스키마:**

```json
{
  "data_fetch_ms": null,
  "feature_compute_ms": null,
  "model_predict_ms": null,
  "decision_ms": null,
  "total_ms": null,
  "measured_at": 1710866096000
}
```

**예제:**

```bash
curl http://localhost:8000/system/latency
```

---

## 제어 (Control)

### GET /control/status

시스템 제어 상태를 반환합니다.

**응답 스키마:**

```json
{
  "running": false,
  "testnet": true,
  "symbol": "BTC/USDT:USDT",
  "timeframe": "30m"
}
```

**예제:**

```bash
curl http://localhost:8000/control/status
```

### POST /control/start

거래 시스템을 시작합니다.

**요청 본문:** 없음

**응답 스키마:**

```json
{
  "success": true,
  "message": "System started"
}
```

**예제:**

```bash
curl -X POST http://localhost:8000/control/start
```

### POST /control/stop

거래 시스템을 중지합니다.

**요청 본문:** 없음

**응답 스키마:**

```json
{
  "success": true,
  "message": "System stopped"
}
```

**예제:**

```bash
curl -X POST http://localhost:8000/control/stop
```

### POST /control/emergency-exit

모든 포지션을 긴급 종료합니다.

**요청 본문:** 없음

**응답 스키마:**

```json
{
  "success": true,
  "message": "Emergency exit triggered — all positions closed"
}
```

**예제:**

```bash
curl -X POST http://localhost:8000/control/emergency-exit
```

### POST /control/set-leverage

레버리지를 변경합니다.

**요청 본문:**

```json
{
  "leverage": 5
}
```

**응답 스키마:**

```json
{
  "success": true,
  "message": "Leverage set to 5x"
}
```

**유효 범위:** 1-125

**예제:**

```bash
curl -X POST http://localhost:8000/control/set-leverage \
  -H "Content-Type: application/json" \
  -d '{"leverage": 5}'
```

### POST /control/force-retrain

모델 재훈련을 강제로 시작합니다.

**요청 본문:** 없음

**응답 스키마:**

```json
{
  "success": true,
  "message": "Model retraining triggered"
}
```

**예제:**

```bash
curl -X POST http://localhost:8000/control/force-retrain
```

---

## 에러 처리

모든 에러는 HTTP 상태 코드와 JSON 본문으로 반환됩니다:

```json
{
  "detail": "Error description"
}
```

**일반적인 상태 코드:**

| 코드 | 설명 |
|------|------|
| 200 | 성공 |
| 400 | 잘못된 요청 (쿼리/본문 파라미터 오류) |
| 404 | 리소스를 찾을 수 없음 |
| 500 | 서버 오류 |

---

## 인증

현재 Aegis API는 인증을 요구하지 않습니다. 프로덕션 배포 전에 인증 메커니즘(예: API 키, OAuth2)을 추가하세요.
