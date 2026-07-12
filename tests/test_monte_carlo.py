"""몬테카를로 엔진 검증: BS 일치, 교차검증 판정, 재현성."""
import numpy as np
import pytest
from scipy.stats import norm

from valuation import monte_carlo, payoffs
from valuation.binomial import BinomialParams, price

S0, K, RF, SIGMA, T = 100.0, 100.0, 0.05, 0.3, 5.0
PARAMS = BinomialParams(s0=S0, sigma=SIGMA, rf=RF, maturity=T, steps=1000)


def bs_call(s0, k, r, sigma, t):
    d1 = (np.log(s0 / k) + (r + 0.5 * sigma**2) * t) / (sigma * np.sqrt(t))
    d2 = d1 - sigma * np.sqrt(t)
    return s0 * norm.cdf(d1) - k * np.exp(-r * t) * norm.cdf(d2)


class TestPriceEuropean:
    def test_ci_contains_analytic_value(self):
        mc = monte_carlo.price_european(PARAMS, payoffs.call(K), paths=200_000, seed=42)
        assert mc.contains(bs_call(S0, K, RF, SIGMA, T))

    def test_reproducible_with_same_seed(self):
        a = monte_carlo.price_european(PARAMS, payoffs.call(K), paths=50_000, seed=7)
        b = monte_carlo.price_european(PARAMS, payoffs.call(K), paths=50_000, seed=7)
        assert a.value == b.value
        assert a.std_error == b.std_error

    def test_antithetic_reduces_std_error(self):
        plain = monte_carlo.price_european(
            PARAMS, payoffs.call(K), paths=100_000, seed=1, antithetic=False
        )
        anti = monte_carlo.price_european(
            PARAMS, payoffs.call(K), paths=100_000, seed=1, antithetic=True
        )
        assert anti.std_error < plain.std_error

    def test_invalid_inputs_raise(self):
        with pytest.raises(ValueError):
            monte_carlo.price_european(PARAMS, payoffs.call(K), paths=10)
        with pytest.raises(ValueError):
            monte_carlo.price_european(PARAMS, payoffs.call(K), confidence=1.5)


class TestCrossCheck:
    def test_binomial_passes_cross_check(self):
        binomial_value = price(PARAMS, payoffs.call(K))
        mc = monte_carlo.price_european(PARAMS, payoffs.call(K), paths=200_000, seed=42)
        result = monte_carlo.cross_check(binomial_value, mc)
        assert result["passed"] is True

    def test_wrong_value_fails_cross_check(self):
        mc = monte_carlo.price_european(PARAMS, payoffs.call(K), paths=200_000, seed=42)
        result = monte_carlo.cross_check(mc.value * 1.5, mc)
        assert result["passed"] is False
