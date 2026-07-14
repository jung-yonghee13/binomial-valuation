"""증권별 페이오프 함수.

[이 파일이 하는 일]
"이 증권을 지금 행사하면 얼마를 받는가"를 계산하는 함수를 만들어 준다.
트리 엔진(binomial.py)과 시뮬레이션 엔진(monte_carlo.py)은 여기서 만든 함수를
전달받아 쓸 뿐, 증권이 콜인지 풋인지 CB인지 알지 못한다 (모형과 증권 조건의 분리).

[사용 예]
    from valuation import payoffs
    f = payoffs.call(12500)   # 행사가 12,500원 콜옵션의 페이오프 함수 생성
    f(np.array([10000, 15000]))  # -> [0, 2500]  (주가별 행사가치)

향후 CB(전환사채), RCPS(상환전환우선주)의 전환권·상환권 페이오프도
같은 형태의 함수로 추가하면 엔진 수정 없이 평가할 수 있다.
"""
from __future__ import annotations

from typing import Callable

import numpy as np

# 페이오프 함수의 형태: 주가 배열 -> 행사가치 배열
Payoff = Callable[[np.ndarray], np.ndarray]


def call(strike: float) -> Payoff:
    """콜옵션 페이오프 max(S - K, 0).

    주가 S가 행사가 K보다 높으면 그 차액을, 낮으면 0을 받는다
    (옵션은 권리이므로 불리하면 행사하지 않는다 → 손실은 0에서 멈춘다).
    """
    if strike <= 0:
        raise ValueError("strike(행사가격)는 양수여야 합니다.")

    def payoff(s: np.ndarray) -> np.ndarray:
        return np.maximum(s - strike, 0.0)

    return payoff


def put(strike: float) -> Payoff:
    """풋옵션 페이오프 max(K - S, 0).

    주가 S가 행사가 K보다 낮으면 그 차액을, 높으면 0을 받는다.
    """
    if strike <= 0:
        raise ValueError("strike(행사가격)는 양수여야 합니다.")

    def payoff(s: np.ndarray) -> np.ndarray:
        return np.maximum(strike - s, 0.0)

    return payoff


def strike_schedule(
    base_strike: float, growth_rate: float, step_years: float, steps: int
) -> np.ndarray:
    """시점별 행사가격 스케줄을 만든다 (옵션 대가율이 있는 계약 구조).

    실무 콜옵션 계약에는 "행사 시점까지 연 r%의 수익률(대가)을 보장"하는 조건이
    흔하다. 이 경우 행사가격이 시간이 갈수록 복리로 상승한다:

        K(t) = base_strike × (1 + growth_rate)^t     (t = 경과 연수)

    growth_rate = 0 이면 전 구간 동일한 고정 행사가격이 된다.
    반환: 길이 steps+1 배열 (각 트리 시점의 행사가격).
    """
    if base_strike <= 0:
        raise ValueError("base_strike(기준 행사가격)는 양수여야 합니다.")
    if step_years <= 0 or steps < 1:
        raise ValueError("step_years는 양수, steps는 1 이상이어야 합니다.")
    if growth_rate <= -1:
        raise ValueError("growth_rate(대가율)는 -100% 초과여야 합니다.")

    t = np.arange(steps + 1) * step_years
    return base_strike * (1.0 + growth_rate) ** t


def call_with_schedule(strikes: np.ndarray) -> Payoff:
    """시점별 행사가격이 다른 콜옵션 페이오프.

    strikes: 길이 steps+1 배열 (strike_schedule()로 생성).
    엔진은 이 함수에 (주가 배열, 시점 인덱스)를 넘겨 호출한다
    (time_dependent 속성으로 엔진이 시점 의존 페이오프임을 인식).
    """
    strikes = np.asarray(strikes, dtype=float)
    if strikes.ndim != 1 or len(strikes) < 2:
        raise ValueError("strikes는 길이 2 이상의 1차원 배열이어야 합니다.")
    if np.any(strikes <= 0):
        raise ValueError("행사가격은 모두 양수여야 합니다.")

    def payoff(s: np.ndarray, step: int) -> np.ndarray:
        return np.maximum(s - strikes[step], 0.0)

    payoff.time_dependent = True  # 엔진이 (s, step) 시그니처로 호출하도록 표시
    return payoff


def evaluate(payoff: Payoff, s: np.ndarray, step: int) -> np.ndarray:
    """페이오프를 호출한다 — 시점 의존 여부를 자동 판별한다 (엔진 내부용)."""
    if getattr(payoff, "time_dependent", False):
        return payoff(s, step)
    return payoff(s)
