"""기간구조(선도이자율) 반영 평가 검증: 선도이자율 항등식, 평면 곡선 일치성."""
import numpy as np
import pytest

from valuation import payoffs
from valuation.binomial import BinomialParams, price, price_with_curve
from valuation.risk_free import bootstrap_spot_curve, step_forward_rates

MATURITIES = [0.25, 0.5, 1.0, 2.0, 3.0, 5.0]
WEEK = 7 / 365


class TestStepForwardRates:
    def test_forward_product_recovers_discount_factor(self):
        # (1+f_1)(1+f_2)...(1+f_n) = 1/DF(t_n) 항등식 확인
        yields = [0.02, 0.022, 0.025, 0.027, 0.028, 0.030]
        steps = 52
        forwards = step_forward_rates(MATURITIES, yields, WEEK, steps)
        grid, spots = bootstrap_spot_curve(MATURITIES, yields)
        t_n = steps * WEEK
        df_n = np.exp(-np.interp(t_n, grid, spots) * t_n)
        assert np.prod(1.0 + forwards) == pytest.approx(1.0 / df_n, rel=1e-10)

    def test_flat_curve_gives_flat_forwards(self):
        y = 0.03
        forwards = step_forward_rates(MATURITIES, [y] * len(MATURITIES), WEEK, 20)
        assert np.allclose(forwards, forwards[0])

    def test_invalid_inputs_raise(self):
        with pytest.raises(ValueError):
            step_forward_rates(MATURITIES, [0.03] * len(MATURITIES), -0.1, 10)
        with pytest.raises(ValueError):
            step_forward_rates(MATURITIES, [0.03] * len(MATURITIES), WEEK, 0)


class TestPriceWithCurve:
    def test_flat_curve_matches_flat_engine(self):
        # 평면 수익률곡선이면 기간구조 엔진과 고정금리 엔진이 같은 값을 내야 한다
        s0, k, sigma, steps = 100.0, 100.0, 0.4, 104  # 2년 주간 트리
        maturity = steps * WEEK
        r_cont = 0.03  # 연속복리

        flat = price(
            BinomialParams(s0=s0, sigma=sigma, rf=r_cont, maturity=maturity, steps=steps),
            payoffs.call(k),
            american=True,
        )
        # 고정 연속복리 금리와 동치인 스텝별 단리 선도이자율
        step_rate = np.exp(r_cont * WEEK) - 1.0
        curve = price_with_curve(
            s0, sigma, WEEK, np.full(steps, step_rate), payoffs.call(k), american=True
        )
        assert curve == pytest.approx(flat, rel=1e-9)

    def test_upward_curve_call_worth_more_than_low_flat(self):
        # 우상향 곡선의 콜 가치는 단기금리 고정 평가보다 높다 (금리 상승 -> 콜 가치 증가)
        s0, k, sigma, steps = 100.0, 100.0, 0.4, 104
        rising = np.linspace(0.0004, 0.0012, steps)  # 주간 단리 상승 곡선
        low_flat = np.full(steps, 0.0004)
        assert price_with_curve(s0, sigma, WEEK, rising, payoffs.call(k)) > price_with_curve(
            s0, sigma, WEEK, low_flat, payoffs.call(k)
        )

    def test_no_arbitrage_violation_raises(self):
        with pytest.raises(ValueError, match="무차익거래"):
            # 주간 이자율 10%는 상승배수를 초과 -> 위반
            price_with_curve(100, 0.05, WEEK, np.full(10, 0.10), payoffs.call(100))

    def test_invalid_inputs_raise(self):
        with pytest.raises(ValueError):
            price_with_curve(100, 0.3, WEEK, np.array([]), payoffs.call(100))
        with pytest.raises(ValueError):
            price_with_curve(-1, 0.3, WEEK, np.full(10, 0.001), payoffs.call(100))
