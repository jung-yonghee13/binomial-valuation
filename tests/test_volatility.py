"""변동성 산출 검증 (네트워크 없이 합성 데이터로 검증)."""
import numpy as np
import pytest

from valuation.volatility import annualized_volatility


class TestAnnualizedVolatility:
    def test_recovers_known_sigma_from_gbm(self):
        # 알려진 sigma로 생성한 GBM 시계열에서 변동성이 복원되는지 확인
        rng = np.random.default_rng(0)
        sigma, n = 0.3, 252 * 4
        daily = sigma / np.sqrt(252)
        log_returns = rng.normal(0.0, daily, size=n)
        prices = 100 * np.exp(np.cumsum(log_returns))
        assert annualized_volatility(prices) == pytest.approx(sigma, rel=0.05)

    def test_constant_prices_zero_volatility(self):
        assert annualized_volatility(np.full(100, 50.0)) == pytest.approx(0.0)

    def test_too_few_observations_raise(self):
        with pytest.raises(ValueError, match="부족"):
            annualized_volatility(np.arange(1, 11, dtype=float))

    def test_nonpositive_prices_raise(self):
        prices = np.concatenate([np.full(50, 10.0), [0.0], np.full(50, 10.0)])
        with pytest.raises(ValueError):
            annualized_volatility(prices)
