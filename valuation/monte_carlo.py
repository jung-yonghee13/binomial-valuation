"""몬테카를로 교차검증 엔진.

이항모형과 동일한 위험중립 GBM 가정 하에서 경로 시뮬레이션으로 독립 계산하여
이항모형 평가액의 신뢰성을 검증한다 (계산의 정확성 검증).
- 난수 시드 고정으로 재현성 확보
- 대조변량(antithetic variates)으로 분산 감소
- 유럽형 페이오프 전용 (조기행사·경로의존 조건은 추후 LSMC로 확장)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import norm

from valuation.binomial import BinomialParams, Payoff


@dataclass(frozen=True)
class MonteCarloResult:
    value: float
    std_error: float
    ci_low: float
    ci_high: float
    paths: int
    seed: int
    confidence: float

    def contains(self, x: float) -> bool:
        """x가 신뢰구간 내에 있는지 여부."""
        return self.ci_low <= x <= self.ci_high


def price_european(
    params: BinomialParams,
    payoff: Payoff,
    paths: int = 100_000,
    seed: int = 42,
    antithetic: bool = True,
    confidence: float = 0.95,
) -> MonteCarloResult:
    """유럽형 옵션 1주당 가치를 위험중립 GBM 시뮬레이션으로 계산한다."""
    if paths < 100:
        raise ValueError("paths(경로 수)는 100 이상이어야 합니다.")
    if not 0 < confidence < 1:
        raise ValueError("confidence(신뢰수준)는 (0, 1) 사이여야 합니다.")

    rng = np.random.default_rng(seed)
    if antithetic:
        half = paths // 2
        z = rng.standard_normal(half)
        z = np.concatenate([z, -z])
    else:
        z = rng.standard_normal(paths)

    t = params.maturity
    drift = (params.rf - params.dividend_yield - 0.5 * params.sigma**2) * t
    s_t = params.s0 * np.exp(drift + params.sigma * np.sqrt(t) * z)
    discounted = np.exp(-params.rf * t) * np.asarray(payoff(s_t), dtype=float)

    value = float(discounted.mean())
    if antithetic:
        # 대조변량 쌍은 독립이 아니므로 쌍 평균 기준으로 표준오차를 계산한다
        pair_means = 0.5 * (discounted[:half] + discounted[half:])
        std_error = float(pair_means.std(ddof=1) / np.sqrt(half))
    else:
        std_error = float(discounted.std(ddof=1) / np.sqrt(paths))

    z_crit = float(norm.ppf(0.5 + confidence / 2.0))
    return MonteCarloResult(
        value=value,
        std_error=std_error,
        ci_low=value - z_crit * std_error,
        ci_high=value + z_crit * std_error,
        paths=len(z),
        seed=seed,
        confidence=confidence,
    )


def cross_check(model_value: float, mc: MonteCarloResult) -> dict:
    """이항모형 평가액이 몬테카를로 신뢰구간 내에 있는지 판정한다.

    반환 dict는 보고서 '평가결과' 장에 그대로 수록할 수 있는 형태이다.
    """
    return {
        "model_value": model_value,
        "mc_value": mc.value,
        "mc_std_error": mc.std_error,
        "confidence": mc.confidence,
        "ci": [mc.ci_low, mc.ci_high],
        "paths": mc.paths,
        "seed": mc.seed,
        "passed": mc.contains(model_value),
    }
