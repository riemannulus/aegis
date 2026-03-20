# 백오피스 가이드

Aegis 백오피스는 Streamlit 기반의 실시간 모니터링 및 제어 대시보드입니다. 거래 시스템의 모든 측면을 시각화하고 관리할 수 있습니다.

## 접속

```bash
# Streamlit로 직접 실행
uv run streamlit run backoffice/app.py --server.port 8501

# Docker로 실행 (API 서버가 필요함)
docker compose up
```

**URL**: http://localhost:8501

## 대시보드 개요

백오피스는 8개 페이지로 구성되어 있습니다:

| 페이지 | 설명 |
|--------|------|
| **01 Live Dashboard** | 실시간 시스템 상태, 현재 포지션, 자산 곡선 |
| **02 Decision Log** | 모든 거래 의사결정 기록 및 근거 |
| **03 Trade Journal** | 개별 거래 분석 및 차트 |
| **04 PnL Analytics** | 성과 지표, 손익 분석, 기여도 분석 |
| **05 Model Monitor** | IC 추이, 특성 중요도, 드리프트 감지 |
| **06 Risk Dashboard** | 낙폭 게이지, 리스크 수준, 이벤트 히스토리 |
| **07 Backtest Viewer** | 백테스트 결과 비교, 실시간 성과 오버레이 |
| **08 System Ops** | 시스템 로그, 지연시간, 수동 제어 |

---

## 페이지 상세 가이드

### Page 1: Live Dashboard (실시간 대시보드)

**목적**: 시스템의 실시간 건강 상태를 한눈에 파악합니다.

**주요 요소:**

1. **시스템 상태 (Status)**
   - API 서버 연결 상태
   - 모델 로드 여부
   - 마지막 신호 시간
   - 데이터베이스 크기

2. **현재 포지션 (Current Position)**
   - 포지션 방향 (Long/Short/Flat)
   - 사이즈
   - 진입 가격
   - 현재 손익 (실현 / 미실현)

3. **자산 곡선 (Equity Curve)**
   - 누적 손익 추이 (시간대별 그래프)
   - 펀딩 수수료 누적

4. **긴급 제어 (Emergency Controls)**
   - **Emergency Exit**: 모든 포지션 즉시 종료
   - **Start/Stop**: 거래 시스템 시작/중지

**사용 시나리오:**
- 거래 중 포지션 모니터링
- 긴급 상황 발생 시 빠른 종료
- 시스템 건강 상태 확인

---

### Page 2: Decision Log (의사결정 기록)

**목적**: 모든 거래 의사결정의 이력 및 근거를 추적합니다.

**기록 항목:**

| 필드 | 설명 |
|------|------|
| **Timestamp** | 의사결정 시간 |
| **Decision** | 의사결정 (EXECUTE / SKIP / REJECTED) |
| **Direction** | 거래 방향 (long / short) |
| **Z-Score** | 신호 강도 (-3 ~ 3 범위) |
| **Regime** | 시장 환경 (trending_up / ranging / trending_down) |
| **Reason** | 의사결정 근거 (텍스트) |

**의사결정 유형:**

- **EXECUTE**: 신호가 강하고 리스크 조건을 만족하여 거래 실행
- **SKIP**: 신호는 있지만 리스크 조건(일일 손실, 최대 낙폭 등)으로 인해 건너뜀
- **REJECTED**: 신호 강도가 약하거나 신뢰도가 낮아 거부

**필터 및 검색:**
- 날짜 범위 선택
- 의사결정 유형별 필터
- 시장 환경별 분석

**사용 시나리오:**
- 거래 논리 감사
- 시스템이 거래를 건너뛴 이유 확인
- 신호 강도의 변화 추적

---

### Page 3: Trade Journal (거래 저널)

**목적**: 개별 거래를 상세 분석합니다.

**거래 정보:**

| 필드 | 설명 |
|------|------|
| **Entry Time** | 진입 시간 |
| **Exit Time** | 청산 시간 |
| **Side** | 방향 (Long / Short) |
| **Size** | 거래량 |
| **Entry Price** | 진입가 |
| **Exit Price** | 청산가 |
| **PnL** | 손익 (금액) |
| **PnL %** | 손익 (수익률) |
| **Duration** | 보유 시간 |
| **Funding Cost** | 펀딩 수수료 |

**차트 분석:**
- 거래별 캔들 차트 (1분 ~ 1시간 단위)
- 진입/청산 포인트 표시
- 이동 평균선, Bollinger Bands 등 기술적 지표

**필터:**
- 날짜 범위
- 손익 구간 (수익 거래 / 손실 거래 / 전체)
- 거래 시간 범위

**통계:**
- 선택된 거래의 평균 손익
- 최대 수익 / 최대 손실 거래
- 평균 보유 기간

**사용 시나리오:**
- 특정 거래의 원인 분석
- 거래 전략 검증
- 패턴 인식 및 개선점 도출

---

### Page 4: PnL Analytics (손익 분석)

**목적**: 성과를 다각도로 분석합니다.

**1. 성과 요약 (Performance Summary)**

| 지표 | 설명 |
|------|------|
| **Total Trades** | 총 거래 수 |
| **Win Rate** | 수익 거래 비율 (%) |
| **Total PnL** | 누적 손익 |
| **Sharpe Ratio** | 위험 조정 수익 (높을수록 좋음) |
| **Sortino Ratio** | 하향 위험만 고려한 지표 |
| **Calmar Ratio** | 수익/최대낙폭 비율 |
| **Max Drawdown** | 최대 낙폭 (%) |

**2. 자산 곡선 (Equity Curve)**
- 누적 손익의 시간대별 추이
- 마커: 주요 거래, 낙폭, 신고점

**3. 손익 분포 (PnL Distribution)**
- 거래별 손익의 히스토그램
- 평균값, 중앙값, 표준편차

**4. 기여도 분석 (Attribution)**

**모델별 기여도:**
- LightGBM 기여 손익
- TRA 기여 손익
- ADARNN 기여 손익

**시장 환경별 기여도:**
- 상승장 (Trending Up)
- 횡보 (Ranging)
- 하락장 (Trending Down)

**시간대별 기여도:**
- 시간 단위로 손익 분석
- 최고 성과 시간대 식별

**5. 월별 성과 (Monthly Performance)**
- 월별 손익 히트맵
- 월별 Sharpe Ratio 비교

**사용 시나리오:**
- 월별 성과 검토
- 모델 기여도 평가
- 최적 거래 시간대 식별

---

### Page 5: Model Monitor (모델 모니터)

**목적**: 모델의 성능과 안정성을 감시합니다.

**1. 최근 훈련 정보 (Training Info)**
- 마지막 훈련 시간
- 다음 예정된 훈련 시간
- 훈련된 모델 목록

**2. IC 추이 (Information Coefficient)**
- 모델 예측과 실제 수익의 상관관계
- IC 커브 (일별 추이)
- Rank IC (순위 기반 IC)

IC가 높을수록 모델의 예측력이 우수합니다.

**3. 특성 중요도 (Feature Importance)**
- 모델 결정에 가장 영향력 있는 특성
- 각 특성의 중요도 점수 (0~1)
- 상위 10개 특성 표시

**주요 특성 예:**
- RSI (Relative Strength Index)
- MACD (Moving Average Convergence Divergence)
- Bollinger Bands 폭
- 거래량 비율
- 변동성

**4. 드리프트 감지 (Prediction Drift)**
- 예측값 분포의 변화
- 예측값 평균의 추이
- 드리프트 수준 경고 (정상 / 주의 / 경고)

드리프트가 높으면 모델 재훈련 필요 시점입니다.

**5. 앙상블 분석 (Ensemble Analysis)**
- 개별 모델 성과 비교
  - LightGBM 방향성 정확도
  - TRA 라우터 활동
  - ADARNN 신호 강도
- 앙상블 방법론 설명

**6. 재훈련 컨트롤 (Retrain Control)**
- **Force Retrain** 버튼: 즉시 모델 재훈련 시작
- 자동 재훈련 간격 설정

**사용 시나리오:**
- 모델 성능 악화 감지 시 재훈련
- IC 급격한 하락 시 조사
- 드리프트 모니터링

---

### Page 6: Risk Dashboard (리스크 대시보드)

**목적**: 리스크 상태를 시각화하고 관리합니다.

**1. 리스크 지표 (Risk Status)**

**낙폭 게이지 (Drawdown Gauge)**
- 현재 최대 낙폭 (%)
- 게이지 색상:
  - 🟢 초록: < 7% (Low)
  - 🟡 노랑: 7-15% (Medium)
  - 🔴 빨강: > 15% (High)

**일일 손실 (Daily Loss)**
- 당일 누적 손실
- 일일 손실 한도(Daily Loss Budget) 대비 비율

**연속 손실 (Consecutive Losses)**
- 연속된 손실 거래 수
- 과도한 연속 손실 시 거래 중지 권장

**포지션 비율 (Position Ratio)**
- 현재 포지션 규모 / 계좌 잔액 비율
- 과도한 포지션 크기 경고

**2. 리스크 이벤트 히스토리 (Risk Events)**

| 이벤트 | 설명 |
|--------|------|
| **Drawdown Alert** | 최대 낙폭 임계값 초과 |
| **Daily Loss Limit** | 일일 손실 한도 도달 |
| **Consecutive Losses** | 연속 손실 거래 발생 |
| **Position Close** | 리스크로 인한 포지션 강제 청산 |

**3. 리스크 관리 정책 (Risk Policies)**

**포지션 제한:**
- 최대 포지션 크기
- 최대 레버리지

**손실 한도:**
- 일일 손실 한도
- 최대 낙폭 한도

**거래 제한:**
- 연속 손실 시 자동 중지
- 고 변동성 시 거래량 감소

**사용 시나리오:**
- 실시간 리스크 모니터링
- 과도한 손실 시나리오 조기 감지
- 리스크 정책 조정

---

### Page 7: Backtest Viewer (백테스트 뷰어)

**목적**: 백테스트 결과를 분석하고 실시간 성과와 비교합니다.

**1. 백테스트 선택 (Backtest Selection)**
- 이용 가능한 백테스트 목록
- 백테스트 날짜 및 파라미터 표시

**2. 성과 비교 (Performance Comparison)**

| 메트릭 | 백테스트 | 실시간 |
|--------|---------|--------|
| **Total Trades** | - | - |
| **Win Rate** | - | - |
| **Total PnL** | - | - |
| **Sharpe** | - | - |
| **Max Drawdown** | - | - |

**차이점 분석:**
- 백테스트 대비 실시간 성과 편차
- 원인 분석 (시장 변화, 슬리피지 등)

**3. 자산 곡선 오버레이 (Equity Curve Overlay)**
- 백테스트 자산 곡선
- 실시간 자산 곡선 (같은 기간 기준)
- 시각적 비교

**4. 거래 비교 (Trade Comparison)**
- 백테스트 거래 목록
- 실시간 거래 목록
- 동일 신호에 대한 실행 여부 비교

**5. 드래우다운 분석 (Drawdown Analysis)**
- 백테스트 드래우다운 프로파일
- 실시간 드래우다운
- 최악의 경우 드래우다운 비교

**사용 시나리오:**
- 모델 성능 검증 (백테스트 vs 실시간)
- 새 모델 백테스트 후 배포 전 검토
- 시장 변화에 따른 성과 편차 분석

---

### Page 8: System Ops (시스템 운영)

**목적**: 시스템 상태 모니터링 및 수동 제어를 수행합니다.

**1. 시스템 로그 (System Logs)**

**로그 레벨 필터:**
- DEBUG, INFO, WARNING, ERROR

**로그 내용:**
- 타임스탬프
- 레벨
- 로거 이름
- 메시지

**사용 예:**
- 오류 원인 추적
- 시스템 이벤트 시간대 확인
- 성능 병목 지점 식별

**2. 지연시간 분석 (Latency Waterfall)**

파이프라인의 각 단계 처리 시간:

| 단계 | 설명 | 목표 |
|------|------|------|
| **Data Fetch** | 시장 데이터 수신 시간 | < 100ms |
| **Feature Compute** | 특성 계산 시간 | < 50ms |
| **Model Predict** | 모델 예측 시간 | < 100ms |
| **Decision** | 거래 의사결정 시간 | < 50ms |
| **Total** | 전체 파이프라인 | < 300ms |

**지연시간이 길 경우 확인:**
- 네트워크 지연
- 모델 크기 (재훈련 고려)
- 데이터베이스 쿼리 성능

**3. 스케줄러 상태 (Scheduler Status)**

**활성 작업:**
- 작업명
- 다음 실행 시간
- 마지막 실행 시간
- 상태 (Running / Idle / Error)

**작업 예:**
- 신호 생성 (매 30분)
- 데이터 다운로드 (매 시간)
- 모델 재훈련 (매일)
- 리스크 계산 (실시간)

**4. 수동 제어 (Manual Controls)**

**거래 제어:**
- ✅ **Start Trading**: 거래 시작
- ⏹️ **Stop Trading**: 거래 중지
- 🚨 **Emergency Exit**: 모든 포지션 즉시 종료

**모델 제어:**
- 🔄 **Force Retrain**: 모델 재훈련 시작
- ⚙️ **Set Leverage**: 레버리지 변경

**거래 파라미터:**
- 거래 기호 (BTCUSDT)
- 타임프레임 (30m)
- 환경 (TESTNET / MAINNET)

**사용 시나리오:**
- 시스템 점검 전 거래 중지
- 급격한 시장 변화 시 긴급 종료
- 모델 성능 악화 시 재훈련
- 거래 시간대 제한 (예: 뉴스 공지 전)

---

## 일반적인 워크플로우

### 1. 일일 시작 체크리스트

1. **Live Dashboard** 확인
   - API 연결 상태
   - 모델 로드 여부
   - 시스템 가동 시간

2. **Model Monitor** 확인
   - IC 추이
   - 드리프트 수준
   - 마지막 훈련 시간

3. **Risk Dashboard** 확인
   - 현재 리스크 수준
   - 어제 최대 낙폭

4. **System Ops** 확인
   - 최근 에러 로그
   - 파이프라인 지연시간

### 2. 일중 모니터링

1. **Live Dashboard**: 포지션 및 손익 모니터링
2. **Decision Log**: 거래 의사결정 로그 확인
3. **Risk Dashboard**: 리스크 지표 모니터링

### 3. 주간 분석

1. **PnL Analytics**: 주간 성과 리뷰
2. **Backtest Viewer**: 실시간 성과 vs 백테스트 비교
3. **Model Monitor**: 모델 성능 추이 분석

### 4. 월간 검토

1. **PnL Analytics**: 월간 성과 보고서
2. **Trade Journal**: 거래 패턴 분석
3. **Model Monitor**: 재훈련 필요 여부 판단

---

## 팁 및 베스트 프랙티스

### 성과 개선
- **Decision Log**에서 SKIP된 거래 확인: 거래 조건 조정 기회 식별
- **Trade Journal**에서 반복되는 손실 패턴 찾기
- **PnL Analytics**에서 최고 성과 시간대 집중

### 리스크 관리
- **Risk Dashboard**를 1시간마다 확인
- 최대 낙폭이 15%를 초과하면 매매 중지 고려
- 연속 손실이 5건을 초과하면 문제 분석

### 모델 관리
- **Model Monitor**에서 IC가 0.05 이하 떨어지면 재훈련
- Prediction Drift가 "경고" 상태면 즉시 재훈련
- Feature Importance에서 주요 특성의 중요도 추이 모니터

### 문제 해결
- API 연결 오류: **System Ops** > Logs에서 "ERROR" 로그 확인
- 거래 누락: **Decision Log**에서 SKIP 이유 확인
- 느린 거래 실행: **System Ops** > Latency에서 병목 단계 식별
