"""CRR 이항모형 트리 엔진 — 벡터화된 역방향 귀납.

설계 원칙 (README 참조):
- 위험중립확률과 할인계수는 동일한 연속복리 기준을 사용한다.
- 입력 검증 실패 시 계산 전에 예외를 발생시킨다.
- 페이오프 함수를 인자로 받아 모형과 증권 조건을 분리한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

Payoff = Callable[[np.ndarray], np.ndarray]


@dataclass(frozen=True)
class BinomialParams:
    """이항모형 입력 파라미터.

    rf(무위험이자율)와 dividend_yield(배당수익률)는 연속복리 기준 연율.
    sigma는 연환산 변동성, maturity는 연 단위 잔존만기.
    """

    s0: float
    sigma: float
    rf: float
    maturity: float
    steps: int
    dividend_yield: float = 0.0

    def __post_init__(self) -> None:
        if self.s0 <= 0:
            raise ValueError("s0(현재 주가)는 양수여야 합니다.")
        if self.sigma <= 0:
            raise ValueError("sigma(변동성)는 양수여야 합니다.")
        if self.maturity <= 0:
            raise ValueError("maturity(잔존만기)는 양수여야 합니다.")
        if self.steps < 1:
            raise ValueError("steps(트리 스텝 수)는 1 이상의 정수여야 합니다.")
        growth = np.exp((self.rf - self.dividend_yield) * self.dt)
        if not (self.d < growth < self.u):
            raise ValueError(
                "무차익거래 조건 위반: 위험중립확률이 (0, 1)을 벗어납니다. "
                "스텝 수를 늘리거나 입력 파라미터를 확인하세요."
            )

    @property
    def dt(self) -> float:
        return self.maturity / self.steps

    @property
    def u(self) -> float:
        return float(np.exp(self.sigma * np.sqrt(self.dt)))

    @property
    def d(self) -> float:
        return 1.0 / self.u

    @property
    def q(self) -> float:
        growth = np.exp((self.rf - self.dividend_yield) * self.dt)
        return float((growth - self.d) / (self.u - self.d))


def price(params: BinomialParams, payoff: Payoff, american: bool = False) -> float:
    """CRR 이항모형으로 옵션 1주당 현재가치를 계산한다.

    만기 시점 주가 배열에서 출발해 배열 연산으로 한 스텝씩 역방향 이동한다.
    메모리 O(steps), 트리 행렬을 만들지 않는다.
    """
    disc = np.exp(-params.rf * params.dt)
    j = np.arange(params.steps + 1)
    s = params.s0 * params.u ** j * params.d ** (params.steps - j)
    v = np.asarray(payoff(s), dtype=float)

    for _ in range(params.steps):
        s = s[1:] * params.d  # 직전 시점의 주가 배열 (u·d = 1 이용)
        v = disc * (params.q * v[1:] + (1.0 - params.q) * v[:-1])
        if american:
            v = np.maximum(v, payoff(s))

    return float(v[0])


def build_trees(
    params: BinomialParams, payoff: Payoff, american: bool = False
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """보고서 예시용 전체 트리(주가, 행사가치, 옵션가치)를 생성한다.

    메모리를 O(steps^2) 사용하므로 소규모 스텝(예시·검증 용도)에만 쓴다.
    행 j = 상승 횟수, 열 t = 경과 스텝. j > t 영역은 NaN.
    """
    n = params.steps
    stock = np.full((n + 1, n + 1), np.nan)
    for t in range(n + 1):
        j = np.arange(t + 1)
        stock[: t + 1, t] = params.s0 * params.u ** j * params.d ** (t - j)

    exercise = payoff(stock)  # NaN은 payoff를 거쳐도 NaN으로 유지된다

    value = np.full((n + 1, n + 1), np.nan)
    value[:, n] = exercise[:, n]
    disc = np.exp(-params.rf * params.dt)
    for t in range(n - 1, -1, -1):
        cont = disc * (
            params.q * value[1 : t + 2, t + 1]
            + (1.0 - params.q) * value[: t + 1, t + 1]
        )
        if american:
            value[: t + 1, t] = np.maximum(cont, exercise[: t + 1, t])
        else:
            value[: t + 1, t] = cont

    return stock, exercise, value
