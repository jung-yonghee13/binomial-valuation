"""몬테카를로 교차검증 엔진.

[이 파일이 하는 일]
이항모형과 "동일한 가정, 완전히 다른 계산 방식"으로 옵션가치를 독립 계산해서
이항모형 평가액이 믿을 만한지 검증한다.

- 이항모형: 격자(트리)를 만들어 역방향으로 할인 (binomial.py)
- 몬테카를로: 주가의 미래 경로를 수만 번 무작위로 만들어 페이오프의 평균을 할인

두 방식의 결과가 통계적으로 일치하면 "계산이 정확하다"는 강한 근거가 된다.
(단, 이것은 계산의 정확성 검증이지 변동성·할인율 같은 가정의 타당성 검증이 아니다)

[신뢰성을 위한 장치]
- 난수 시드 고정: 같은 입력이면 언제 다시 돌려도 같은 결과 (보고서 재현성)
- 대조변량(antithetic variates): 난수 Z와 -Z를 쌍으로 사용해 추정 오차를 줄임
- 95% 신뢰구간 제공: "이항모형 값이 이 구간 안에 있는가"로 합격/불합격 판정

[한계]
유럽형(만기에만 행사) 전용이다. 미국형 조기행사나 리픽싱 같은 경로의존 조건은
Longstaff-Schwartz 회귀(LSMC)가 필요하며 추후 확장 예정.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import norm

from valuation import payoffs as payoffs_mod
from valuation.binomial import BinomialParams, Payoff


@dataclass(frozen=True)
class MonteCarloResult:
    """몬테카를로 계산 결과 묶음 (보고서에 그대로 수록되는 값들)."""

    value: float       # 옵션 1주당 가치 추정치 (경로 평균)
    std_error: float   # 표준오차 (추정치의 통계적 불확실성)
    ci_low: float      # 신뢰구간 하한
    ci_high: float     # 신뢰구간 상한
    paths: int         # 사용한 경로 수
    seed: int          # 난수 시드 (재현용)
    confidence: float  # 신뢰수준 (예: 0.95)

    def contains(self, x: float) -> bool:
        """x(이항모형 평가액)가 신뢰구간 안에 있는지 — 교차검증 합격 여부."""
        return self.ci_low <= x <= self.ci_high


def price_european(
    params: BinomialParams,
    payoff: Payoff,
    paths: int = 100_000,
    seed: int = 42,
    antithetic: bool = True,
    confidence: float = 0.95,
) -> MonteCarloResult:
    """유럽형 옵션 1주당 가치를 위험중립 GBM 시뮬레이션으로 계산한다.

    [계산 절차]
    1. 표준정규 난수 Z를 경로 수만큼 생성
    2. 만기 주가 공식으로 각 경로의 만기 주가를 계산 (기하브라운운동 GBM 가정)
       S_T = S0 · exp[(rf - 배당 - σ²/2)·T + σ·√T·Z]
    3. 각 경로의 페이오프를 구해 무위험이자율로 할인
    4. 전체 경로의 평균 = 옵션가치 추정치, 표준오차로 신뢰구간 계산
    """
    if paths < 100:
        raise ValueError("paths(경로 수)는 100 이상이어야 합니다.")
    if not 0 < confidence < 1:
        raise ValueError("confidence(신뢰수준)는 (0, 1) 사이여야 합니다.")

    # 시드를 고정한 난수 생성기 → 같은 시드면 항상 같은 난수 (재현성)
    rng = np.random.default_rng(seed)
    if antithetic:
        # 대조변량: Z와 -Z를 쌍으로 쓰면 한쪽의 과대추정을 반대쪽이 상쇄해
        # 같은 경로 수로 더 정확한 추정치를 얻는다 (분산감소기법)
        half = paths // 2
        z = rng.standard_normal(half)
        z = np.concatenate([z, -z])
    else:
        z = rng.standard_normal(paths)

    # 만기 주가 (위험중립 GBM). -0.5σ²T 는 로그정규분포의 평균 보정항
    t = params.maturity
    drift = (params.rf - params.dividend_yield - 0.5 * params.sigma**2) * t
    s_t = params.s0 * np.exp(drift + params.sigma * np.sqrt(t) * z)

    # 경로별 페이오프를 현재가치로 할인
    # 유럽형이므로 만기 시점(스케줄의 마지막 원소)의 행사가격을 적용한다
    exercise = payoffs_mod.evaluate(payoff, s_t, -1)
    discounted = np.exp(-params.rf * t) * np.asarray(exercise, dtype=float)

    value = float(discounted.mean())  # 옵션가치 = 할인 페이오프의 평균

    # 표준오차 계산: 대조변량을 썼다면 (Z, -Z) 쌍은 서로 독립이 아니므로
    # 쌍의 평균들을 하나의 표본으로 보고 표준오차를 구해야 통계적으로 올바르다
    if antithetic:
        pair_means = 0.5 * (discounted[:half] + discounted[half:])
        std_error = float(pair_means.std(ddof=1) / np.sqrt(half))
    else:
        std_error = float(discounted.std(ddof=1) / np.sqrt(paths))

    # 신뢰구간: 추정치 ± z값 × 표준오차 (95%면 z값 약 1.96)
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

    passed=True 면 "서로 다른 두 계산 방식이 통계적으로 같은 값을 냈다"는 의미.
    반환 dict는 보고서 '평가결과' 장에 그대로 수록할 수 있는 형태이다.
    """
    return {
        "model_value": model_value,       # 이항모형 평가액
        "mc_value": mc.value,             # 몬테카를로 추정치
        "mc_std_error": mc.std_error,     # 표준오차
        "confidence": mc.confidence,      # 신뢰수준
        "ci": [mc.ci_low, mc.ci_high],    # 신뢰구간
        "paths": mc.paths,
        "seed": mc.seed,
        "passed": mc.contains(model_value),  # 합격 여부
    }
