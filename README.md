# 이항모형 기반 밸류에이션 자동화 (Binomial Model Valuation Automation)

이항모형(Binomial Option Pricing Model)을 파이썬으로 구현하여 옵션성 증권의 가치평가(밸류에이션)를 자동화하는 프로젝트입니다.

전환사채(CB), 상환전환우선주(RCPS) 등 옵션이 내재된 메자닌 증권의 공정가치 평가는 실무에서 주로 엑셀로 수행되지만, 단위기간이 촘촘해지거나(트리 노드 수 증가) 전환가액 조정(리픽싱)·조기상환권 같은 복잡한 조건이 붙으면 엑셀로는 관리가 어렵고 느려집니다. 이 프로젝트는 해당 계산 로직을 파이썬 코드로 옮겨 **재현 가능하고 확장 가능한 평가 파이프라인**을 만드는 것을 목표로 합니다.

## 참고 자료

- 계산 로직 원문(블로그): [파이썬을 이용한 이항모형 옵션가격결정 — pythoncpa](https://pythoncpa.tistory.com/2)
- 참고 코드(Colab): [CRR_option_pricing.ipynb](https://colab.research.google.com/drive/1yap9HfNlKQ0qmMhO6mwM_w7lJyJJyTeB)

## 이론적 배경: CRR 이항모형

Cox-Ross-Rubinstein(1979) 모형은 기초자산(주가)이 매 단위기간마다 일정 배수로 상승(u)하거나 하락(d)한다고 가정하고, 위험중립확률(P)로 만기 페이오프를 역방향으로 할인하여 현재 옵션가치를 구합니다.

| 기호 | 의미 | 예시 값 |
|------|------|---------|
| `S0` | 평가기준일 현재 주가 | 100 |
| `V`  | 주가 변동성 (단위기간 기준) | 0.3 |
| `T`  | 전체 기간 (트리 스텝 수) | 5 |
| `dt` | 단위기간 | 1 |
| `Rf` | 무위험이자율 (이산복리) | 0.05 |
| `K`  | 행사가격 | 100 |

핵심 수식:

```
u = exp(V · √dt)          # 주가 상승배수
d = 1 / u                 # 주가 하락배수
P = (exp(Rf · dt) − d) / (u − d)   # 위험중립확률
```

단위기간(`dt`)을 작게 할수록 계산 결과는 Black-Scholes 모형의 해에 수렴합니다.

## 계산 절차 (참고 코드 로직)

참고 코드는 세 단계로 구성됩니다.

### 1단계 — 기본 파라미터 계산

입력 변수로부터 상승배수 `u`, 하락배수 `d`, 위험중립확률 `P`를 계산합니다.

```python
import math as m

S0, V, T, dt, Rf, K = 100, 0.3, 5, 1, 0.05, 100

u = m.exp(V * m.sqrt(dt))
d = 1 / u
P = (m.exp(Rf * dt) - d) / (u - d)
```

### 2단계 — 주가 트리(Stock Price Tree) 생성

`(T+1) × (T+1)` 상삼각 행렬을 만들어 각 노드에 `S0 · u^(time−node) · d^node`를 채웁니다. 행(`node`)은 하락 횟수, 열(`time`)은 경과 기간을 의미합니다.

```python
import numpy as np
import pandas as pd

S_tree = pd.DataFrame(np.zeros((T + 1, T + 1)))
for node in range(T + 1):
    for time in range(T + 1):
        if time >= node:
            S_tree.loc[node, time] = S0 * m.pow(u, time - node) * m.pow(d, node)
```

### 3단계 — 옵션가치 트리(역방향 귀납, Backward Induction)

각 노드의 내재가치(행사가치) `max(S − K, 0)`를 구한 뒤, 만기 시점부터 현재 시점까지 위험중립확률로 기대값을 만들어 무위험이자율로 할인합니다. 각 노드에서는 **계속보유가치와 행사가치 중 큰 값**을 취합니다(미국형 옵션 대응).

```python
# 내재가치(행사가치) 트리
C_K_tree = pd.DataFrame(np.zeros((T + 1, T + 1)))
for node in range(T + 1):
    for time in range(T + 1):
        if time >= node:
            C_K_tree.loc[node, time] = max(S_tree.loc[node, time] - K, 0)

# 옵션가치 트리 — 만기 페이오프에서 출발해 역방향 할인
C_tree = pd.DataFrame(np.zeros((T + 1, T + 1)))
C_tree[T] = C_K_tree[T]
for node in range(T - 1, -1, -1):
    for time in range(T - 1, -1, -1):
        if time >= node:
            continuation = (P * C_tree.loc[node, time + 1]
                            + (1 - P) * C_tree.loc[node + 1, time + 1]) / (1 + Rf)
            C_tree.loc[node, time] = max(continuation, C_K_tree.loc[node, time])
```

`C_tree.loc[0, 0]`이 평가기준일 현재의 옵션가치이며, 위 예시 입력으로는 콜옵션 가치가 약 **37**로 산정됩니다.

## 자동화 로드맵

참고 코드를 출발점으로 아래 방향으로 확장할 예정입니다. 세부 구현과 엔지니어링은 단계적으로 진행합니다.

- [ ] **모듈화**: 노트북 코드를 함수/클래스 기반 파이썬 패키지로 재구성 (`build_stock_tree`, `price_option` 등)
- [ ] **성능 개선**: 이중 for문을 numpy 벡터 연산으로 대체하여 트리 스텝 수가 큰 경우에도 빠르게 계산
- [ ] **검증**: Black-Scholes 해석해와의 수렴 테스트, 엑셀 평가모델과의 대사(reconciliation)
- [ ] **증권별 페이오프 확장**: 콜/풋, 미국형/유럽형, 전환사채(CB), 상환전환우선주(RCPS)의 전환권·상환권·조기상환권(콜/풋) 반영
- [ ] **조건 반영**: 전환가액 조정(리픽싱), 배당, 희석효과 등 실무 평가조건 반영
- [ ] **입력 자동화**: 평가 파라미터(변동성, 무위험이자율 등)의 외부 데이터 연동 및 입력 템플릿(엑셀/CSV) 지원
- [ ] **결과 출력**: 평가조서에 활용 가능한 트리·요약 결과의 엑셀/리포트 출력

## 프로젝트 구조 (예정)

```
이항모형/
├── README.md            # 프로젝트 개요 (현재 문서)
├── src/                 # 평가 로직 패키지 (예정)
├── notebooks/           # 실험/검증용 노트북 (예정)
└── tests/               # 검증 테스트 (예정)
```
