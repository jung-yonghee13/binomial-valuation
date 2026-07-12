"""증권별 페이오프 함수.

각 함수는 주가 배열을 받아 행사가치 배열을 반환하는 페이오프를 만들어 준다.
트리/시뮬레이션 엔진은 페이오프의 내용을 알지 못한다 (모형과 증권 조건의 분리).
"""
from __future__ import annotations

from typing import Callable

import numpy as np

Payoff = Callable[[np.ndarray], np.ndarray]


def call(strike: float) -> Payoff:
    """콜옵션 페이오프 max(S - K, 0)."""
    if strike <= 0:
        raise ValueError("strike(행사가격)는 양수여야 합니다.")

    def payoff(s: np.ndarray) -> np.ndarray:
        return np.maximum(s - strike, 0.0)

    return payoff


def put(strike: float) -> Payoff:
    """풋옵션 페이오프 max(K - S, 0)."""
    if strike <= 0:
        raise ValueError("strike(행사가격)는 양수여야 합니다.")

    def payoff(s: np.ndarray) -> np.ndarray:
        return np.maximum(strike - s, 0.0)

    return payoff
