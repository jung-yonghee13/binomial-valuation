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
