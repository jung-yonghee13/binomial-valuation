"""CRR 이항모형 트리 엔진 — 벡터화된 역방향 귀납.

[이 파일이 하는 일]
옵션의 현재가치를 Cox-Ross-Rubinstein(1979) 이항모형으로 계산한다.
엑셀로 치면 "주가 트리 시트 + 옵션가치 트리 시트 + 역산 수식" 전체에 해당한다.

[계산 원리 요약]
1. 주가는 매 단위기간(dt)마다 u배로 오르거나 d배로 내린다고 가정한다.
2. 만기 시점의 각 노드에서 옵션의 행사가치(페이오프)를 구한다.
3. 위험중립확률 q로 기대값을 만들어 무위험이자율로 한 스텝씩 현재까지 할인한다.
   (미국형이면 각 노드에서 "계속보유가치 vs 즉시행사가치" 중 큰 값을 취한다)

[설계 원칙 (README 참조)]
- 위험중립확률과 할인계수는 동일한 연속복리 기준을 사용한다.
- 입력이 잘못되면 계산 전에 예외를 발생시킨다 (조용히 틀린 값을 내지 않는다).
- 페이오프 함수를 인자로 받아 "모형"과 "증권 조건"을 분리한다.
  → 콜/풋/CB/RCPS 어떤 증권이든 이 엔진은 수정 없이 재사용된다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

# 페이오프 함수의 형태: 주가 배열을 받아 행사가치 배열을 돌려준다.
# 예: 행사가 100인 콜옵션이면 payoff([90, 110]) -> [0, 10]
Payoff = Callable[[np.ndarray], np.ndarray]


@dataclass(frozen=True)  # frozen=True: 생성 후 값 변경 불가 → 평가 도중 파라미터가 바뀌는 사고 방지
class BinomialParams:
    """이항모형 입력 파라미터 묶음.

    s0             : 평가기준일 현재 기초자산(주식) 가격
    sigma          : 연환산 변동성 (예: 0.3 = 30%)
    rf             : 무위험이자율, 연속복리 기준 연율 (예: 0.05 = 5%)
    maturity       : 잔존만기, 연 단위 (예: 2.5 = 2년 6개월)
    steps          : 트리 스텝 수. 클수록 정확하고(Black-Scholes에 수렴) 느려짐. 실무 기본 1,000
    dividend_yield : 연속 배당수익률 (배당이 없으면 0)
    """

    s0: float
    sigma: float
    rf: float
    maturity: float
    steps: int
    dividend_yield: float = 0.0

    def __post_init__(self) -> None:
        # ── 입력 검증: 잘못된 입력은 여기서 즉시 실패시킨다 ──
        if self.s0 <= 0:
            raise ValueError("s0(현재 주가)는 양수여야 합니다.")
        if self.sigma <= 0:
            raise ValueError("sigma(변동성)는 양수여야 합니다.")
        if self.maturity <= 0:
            raise ValueError("maturity(잔존만기)는 양수여야 합니다.")
        if self.steps < 1:
            raise ValueError("steps(트리 스텝 수)는 1 이상의 정수여야 합니다.")
        # 무차익거래 조건: d < 무위험 성장배수 < u 가 성립해야
        # 위험중립확률 q가 0~1 사이의 "확률"이 된다. 깨지면 모형 자체가 무의미.
        growth = np.exp((self.rf - self.dividend_yield) * self.dt)
        if not (self.d < growth < self.u):
            raise ValueError(
                "무차익거래 조건 위반: 위험중립확률이 (0, 1)을 벗어납니다. "
                "스텝 수를 늘리거나 입력 파라미터를 확인하세요."
            )

    @property
    def dt(self) -> float:
        """단위기간(년). 잔존만기를 스텝 수로 나눈 것."""
        return self.maturity / self.steps

    @property
    def u(self) -> float:
        """주가 상승배수. u = exp(σ√dt) — 주가의 변동폭이 변동성 σ와 일치하도록 정한 값."""
        return float(np.exp(self.sigma * np.sqrt(self.dt)))

    @property
    def d(self) -> float:
        """주가 하락배수. CRR 모형은 d = 1/u 로 두어 트리가 재결합(오르고 내리면 제자리)한다."""
        return 1.0 / self.u

    @property
    def q(self) -> float:
        """위험중립확률.

        '위험중립 세계'에서는 주식의 기대수익률이 무위험이자율과 같아야 하므로
        q·u + (1-q)·d = exp((rf-배당)·dt) 를 풀면 q = (성장배수 - d) / (u - d).
        실제 상승확률이 아니라 할인 계산을 위한 가상의 확률이다.
        """
        growth = np.exp((self.rf - self.dividend_yield) * self.dt)
        return float((growth - self.d) / (self.u - self.d))


def price(params: BinomialParams, payoff: Payoff, american: bool = False) -> float:
    """CRR 이항모형으로 옵션 1주당 현재가치를 계산한다.

    american=False : 유럽형 (만기에만 행사 가능)
    american=True  : 미국형 (기간 중 언제든 행사 가능 → 각 노드에서 조기행사 비교)

    [구현 방식]
    (T+1)×(T+1) 트리 행렬 전체를 만들지 않고, "만기 시점의 주가 배열" 하나에서 출발해
    배열 연산으로 한 스텝씩 뒤로 이동한다. 메모리는 O(steps)만 쓰므로
    스텝 수가 수천이어도 빠르다. (엑셀 트리 시트를 통째로 만드는 방식의 개선판)
    """
    disc = np.exp(-params.rf * params.dt)  # 한 스텝 할인계수 (연속복리)

    # 1) 만기 시점의 주가: 상승 j회·하락 (steps-j)회 노드의 주가 = s0 · u^j · d^(steps-j)
    j = np.arange(params.steps + 1)  # j = 0, 1, ..., steps (상승 횟수)
    s = params.s0 * params.u ** j * params.d ** (params.steps - j)

    # 2) 만기 시점의 옵션가치 = 페이오프 (콜이면 max(S-K, 0))
    v = np.asarray(payoff(s), dtype=float)

    # 3) 만기 → 현재로 한 스텝씩 역방향 이동
    for _ in range(params.steps):
        # 직전 시점의 주가 배열: 배열을 한 칸 줄이며 d를 곱하면 된다 (u·d=1 성질 이용)
        s = s[1:] * params.d
        # 계속보유가치 = [q·(위쪽 자식) + (1-q)·(아래쪽 자식)] × 할인계수
        # v[1:]가 위쪽(상승) 자식, v[:-1]가 아래쪽(하락) 자식에 해당
        v = disc * (params.q * v[1:] + (1.0 - params.q) * v[:-1])
        if american:
            # 미국형: 지금 행사하는 것이 더 유리하면 행사가치로 대체
            v = np.maximum(v, payoff(s))

    # 배열이 한 칸씩 줄어 마지막에는 원소 1개 = 현재(t=0) 시점의 옵션가치
    return float(v[0])


def build_trees(
    params: BinomialParams, payoff: Payoff, american: bool = False
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """전체 트리(주가, 행사가치, 옵션가치)를 행렬로 생성한다 — 보고서 예시 표시용.

    price()와 달리 트리 전체를 메모리에 담으므로(O(steps²))
    보고서에 트리를 보여주는 소규모 스텝(예: 5스텝) 용도로만 쓴다.

    행렬 구조: 행 j = 상승 횟수, 열 t = 경과 스텝. j > t 인 칸(도달 불가 노드)은 NaN.
    """
    n = params.steps

    # ── 주가 트리: 각 노드의 주가 = s0 · u^(상승횟수) · d^(하락횟수) ──
    stock = np.full((n + 1, n + 1), np.nan)
    for t in range(n + 1):
        j = np.arange(t + 1)
        stock[: t + 1, t] = params.s0 * params.u ** j * params.d ** (t - j)

    # ── 행사가치 트리: 각 노드에서 즉시 행사했을 때의 가치 ──
    # (NaN 칸은 페이오프를 거쳐도 NaN으로 유지되어 빈칸으로 남는다)
    exercise = payoff(stock)

    # ── 옵션가치 트리: 만기 열에서 출발해 역방향으로 채운다 ──
    value = np.full((n + 1, n + 1), np.nan)
    value[:, n] = exercise[:, n]  # 만기 시점의 옵션가치 = 행사가치
    disc = np.exp(-params.rf * params.dt)
    for t in range(n - 1, -1, -1):
        # 노드 (j, t)의 계속보유가치 = disc × [q·V(j+1, t+1) + (1-q)·V(j, t+1)]
        cont = disc * (
            params.q * value[1 : t + 2, t + 1]
            + (1.0 - params.q) * value[: t + 1, t + 1]
        )
        if american:
            value[: t + 1, t] = np.maximum(cont, exercise[: t + 1, t])
        else:
            value[: t + 1, t] = cont

    return stock, exercise, value
