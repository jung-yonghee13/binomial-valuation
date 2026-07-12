"""이항모형 엔진 검증: Black-Scholes 수렴, 풋-콜 패리티, 경계 조건."""
import numpy as np
import pytest
from scipy.stats import norm

from valuation import payoffs
from valuation.binomial import BinomialParams, build_trees, price

S0, K, RF, SIGMA, T = 100.0, 100.0, 0.05, 0.3, 5.0


def bs_call(s0, k, r, sigma, t, q=0.0):
    d1 = (np.log(s0 / k) + (r - q + 0.5 * sigma**2) * t) / (sigma * np.sqrt(t))
    d2 = d1 - sigma * np.sqrt(t)
    return s0 * np.exp(-q * t) * norm.cdf(d1) - k * np.exp(-r * t) * norm.cdf(d2)


def bs_put(s0, k, r, sigma, t, q=0.0):
    d1 = (np.log(s0 / k) + (r - q + 0.5 * sigma**2) * t) / (sigma * np.sqrt(t))
    d2 = d1 - sigma * np.sqrt(t)
    return k * np.exp(-r * t) * norm.cdf(-d2) - s0 * np.exp(-q * t) * norm.cdf(-d1)


class TestBlackScholesConvergence:
    def test_european_call_converges(self):
        params = BinomialParams(s0=S0, sigma=SIGMA, rf=RF, maturity=T, steps=2000)
        assert price(params, payoffs.call(K)) == pytest.approx(
            bs_call(S0, K, RF, SIGMA, T), abs=0.05
        )

    def test_european_put_converges(self):
        params = BinomialParams(s0=S0, sigma=SIGMA, rf=RF, maturity=T, steps=2000)
        assert price(params, payoffs.put(K)) == pytest.approx(
            bs_put(S0, K, RF, SIGMA, T), abs=0.05
        )

    def test_call_with_dividend_converges(self):
        q = 0.02
        params = BinomialParams(
            s0=S0, sigma=SIGMA, rf=RF, maturity=T, steps=2000, dividend_yield=q
        )
        assert price(params, payoffs.call(K)) == pytest.approx(
            bs_call(S0, K, RF, SIGMA, T, q=q), abs=0.05
        )

    def test_error_shrinks_with_steps(self):
        target = bs_call(S0, K, RF, SIGMA, T)
        coarse = price(
            BinomialParams(s0=S0, sigma=SIGMA, rf=RF, maturity=T, steps=50),
            payoffs.call(K),
        )
        fine = price(
            BinomialParams(s0=S0, sigma=SIGMA, rf=RF, maturity=T, steps=5000),
            payoffs.call(K),
        )
        assert abs(fine - target) < abs(coarse - target)


class TestPutCallParity:
    def test_european_parity(self):
        params = BinomialParams(s0=S0, sigma=SIGMA, rf=RF, maturity=T, steps=500)
        call_v = price(params, payoffs.call(K))
        put_v = price(params, payoffs.put(K))
        assert call_v - put_v == pytest.approx(S0 - K * np.exp(-RF * T), abs=1e-8)

    def test_parity_with_dividend(self):
        q = 0.03
        params = BinomialParams(
            s0=S0, sigma=SIGMA, rf=RF, maturity=T, steps=500, dividend_yield=q
        )
        call_v = price(params, payoffs.call(K))
        put_v = price(params, payoffs.put(K))
        assert call_v - put_v == pytest.approx(
            S0 * np.exp(-q * T) - K * np.exp(-RF * T), abs=1e-8
        )


class TestAmericanFeatures:
    def test_american_call_equals_european_without_dividend(self):
        params = BinomialParams(s0=S0, sigma=SIGMA, rf=RF, maturity=T, steps=500)
        euro = price(params, payoffs.call(K), american=False)
        amer = price(params, payoffs.call(K), american=True)
        assert amer == pytest.approx(euro, abs=1e-8)

    def test_american_put_worth_at_least_european(self):
        params = BinomialParams(s0=S0, sigma=SIGMA, rf=RF, maturity=T, steps=500)
        euro = price(params, payoffs.put(K), american=False)
        amer = price(params, payoffs.put(K), american=True)
        assert amer > euro

    def test_american_put_at_least_intrinsic(self):
        params = BinomialParams(s0=60.0, sigma=SIGMA, rf=RF, maturity=T, steps=500)
        amer = price(params, payoffs.put(K), american=True)
        assert amer >= K - 60.0


class TestBoundaryConditions:
    def test_deep_itm_call_low_vol_approaches_forward_value(self):
        params = BinomialParams(s0=200.0, sigma=0.01, rf=RF, maturity=1.0, steps=500)
        expected = 200.0 - K * np.exp(-RF * 1.0)
        assert price(params, payoffs.call(K)) == pytest.approx(expected, rel=1e-3)

    def test_deep_otm_call_low_vol_worthless(self):
        params = BinomialParams(s0=10.0, sigma=0.01, rf=RF, maturity=1.0, steps=500)
        assert price(params, payoffs.call(K)) == pytest.approx(0.0, abs=1e-8)

    def test_invalid_inputs_raise(self):
        with pytest.raises(ValueError):
            BinomialParams(s0=-1, sigma=SIGMA, rf=RF, maturity=T, steps=100)
        with pytest.raises(ValueError):
            BinomialParams(s0=S0, sigma=0.0, rf=RF, maturity=T, steps=100)
        with pytest.raises(ValueError):
            BinomialParams(s0=S0, sigma=SIGMA, rf=RF, maturity=-1, steps=100)
        with pytest.raises(ValueError):
            BinomialParams(s0=S0, sigma=SIGMA, rf=RF, maturity=T, steps=0)

    def test_no_arbitrage_violation_raises(self):
        # 극단적 금리로 exp(rf·dt) > u가 되는 경우
        with pytest.raises(ValueError, match="무차익거래"):
            BinomialParams(s0=S0, sigma=0.05, rf=2.0, maturity=5.0, steps=5)


class TestTreeConsistency:
    def test_build_trees_matches_vectorized_price(self):
        params = BinomialParams(s0=S0, sigma=SIGMA, rf=RF, maturity=T, steps=5)
        for american in (False, True):
            _, _, value = build_trees(params, payoffs.call(K), american=american)
            fast = price(params, payoffs.call(K), american=american)
            assert value[0, 0] == pytest.approx(fast, abs=1e-10)

    def test_reference_case_five_steps(self):
        # 검증된 수기 계산: S0=100, V=0.3, T=5, dt=1, 연속복리 rf=5% 콜옵션
        params = BinomialParams(s0=100, sigma=0.3, rf=0.05, maturity=5, steps=5)
        value = price(params, payoffs.call(100.0), american=True)
        assert 30.0 < value < 45.0
