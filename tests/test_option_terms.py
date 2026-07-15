"""옵션 계약 조건 검증: 행사가격 스케줄(대가율), 행사범위·행사비율 수량 산정."""
import copy

import numpy as np
import pytest

from valuation import payoffs
from valuation.binomial import BinomialParams, build_trees, price
from valuation.run_valuation import run
from tests.test_run_valuation import BASE_INPUTS, CONTRACT, make_inputs

WEEK = 7 / 365


class TestStrikeSchedule:
    def test_zero_growth_is_flat(self):
        strikes = payoffs.strike_schedule(10_000, 0.0, WEEK, 52)
        assert np.allclose(strikes, 10_000)

    def test_compounds_annually(self):
        # 대가율 8%: 1년 후 행사가격은 기준가 × 1.08
        strikes = payoffs.strike_schedule(10_000, 0.08, 1.0, 3)
        assert strikes[0] == pytest.approx(10_000)
        assert strikes[1] == pytest.approx(10_800)
        assert strikes[3] == pytest.approx(10_000 * 1.08**3)

    def test_invalid_inputs_raise(self):
        with pytest.raises(ValueError):
            payoffs.strike_schedule(-1, 0.08, WEEK, 10)
        with pytest.raises(ValueError):
            payoffs.strike_schedule(10_000, 0.08, WEEK, 0)
        with pytest.raises(ValueError):
            payoffs.strike_schedule(10_000, -1.5, WEEK, 10)


class TestCallWithSchedule:
    def test_uses_strike_of_each_step(self):
        strikes = np.array([100.0, 110.0, 120.0])
        payoff = payoffs.call_with_schedule(strikes)
        assert payoff(np.array([130.0]), 0)[0] == pytest.approx(30.0)
        assert payoff(np.array([130.0]), 2)[0] == pytest.approx(10.0)

    def test_flat_schedule_matches_plain_call(self):
        params = BinomialParams(s0=100, sigma=0.3, rf=0.03, maturity=1.0, steps=200)
        flat = payoffs.call_with_schedule(np.full(201, 100.0))
        plain = payoffs.call(100.0)
        for american in (False, True):
            assert price(params, flat, american=american) == pytest.approx(
                price(params, plain, american=american), rel=1e-12
            )

    def test_rising_strike_lowers_value(self):
        # 행사가격이 시간에 따라 오르면 콜 가치는 낮아진다
        params = BinomialParams(s0=100, sigma=0.3, rf=0.03, maturity=2.0, steps=104)
        flat = price(params, payoffs.call(100.0))
        rising = price(
            params,
            payoffs.call_with_schedule(payoffs.strike_schedule(100.0, 0.08, 2.0 / 104, 104)),
        )
        assert rising < flat

    def test_build_trees_applies_schedule_per_column(self):
        params = BinomialParams(s0=100, sigma=0.3, rf=0.03, maturity=1.0, steps=4)
        strikes = payoffs.strike_schedule(100.0, 0.10, 0.25, 4)
        _, exercise, _ = build_trees(params, payoffs.call_with_schedule(strikes), american=True)
        # 행 j = 상승 횟수. 만기(t=4)에 4회 상승한 노드: max(S·u^4 − K(만기), 0)
        top_stock = 100 * params.u**4
        assert exercise[4, 4] == pytest.approx(max(top_stock - strikes[4], 0.0))
        assert exercise[0, 0] == pytest.approx(max(100 - strikes[0], 0.0))


class TestQuantityFromContractTerms:
    def _contract(self, **terms):
        c = copy.deepcopy(CONTRACT)
        c["option_terms"].update(terms)
        return c

    def test_scope_and_allocation_reduce_quantity(self):
        # 150,000주 × 행사범위 35% × 행사비율 40% = 21,000주
        result = run(self._contract(exercise_scope=0.35, allocation_ratio=0.40),
                     make_inputs())
        r = result["results"]
        assert r["total_shares"] == 150_000
        assert r["quantity_shares"] == 21_000
        assert r["total_value_krw"] == pytest.approx(r["unit_value_krw"] * 21_000)

    def test_multiple_holders(self):
        # 대상 150,000주 × 행사범위 35% = 52,500주를 세 보유자가 40/30/30 배분
        result = run(self._contract(exercise_scope=0.35, holders=[
            {"name": "행사자A", "ratio": 0.40},
            {"name": "행사자B", "ratio": 0.30},
            {"name": "행사자C", "ratio": 0.30},
        ]), make_inputs())
        r = result["results"]
        holders = r["holders"]
        assert len(holders) == 3
        assert r["scoped_shares"] == 52_500
        assert holders[0]["quantity_shares"] == 21_000  # 52,500 × 40%
        assert holders[1]["quantity_shares"] == 15_750  # 52,500 × 30%
        # 합계 수량·평가액이 보유자별 합과 일치
        assert r["quantity_shares"] == sum(h["quantity_shares"] for h in holders)
        assert r["total_value_krw"] == pytest.approx(sum(h["value_krw"] for h in holders))
        # 각 보유자 평가액 = 1주당 가치 × 보유자 수량
        for h in holders:
            assert h["value_krw"] == pytest.approx(r["unit_value_krw"] * h["quantity_shares"])

    def test_holders_ratio_over_100_percent_raises(self):
        with pytest.raises(ValueError, match="합계"):
            run(self._contract(holders=[
                {"name": "A", "ratio": 0.6}, {"name": "B", "ratio": 0.6},
            ]), make_inputs())

    def test_holders_override_allocation_ratio(self):
        # holders가 있으면 allocation_ratio는 무시된다
        result = run(self._contract(
            exercise_scope=1.0, allocation_ratio=0.99,
            holders=[{"name": "A", "ratio": 0.5}],
        ), make_inputs())
        assert result["results"]["quantity_shares"] == 75_000  # 150,000 × 100% × 50%

    def test_defaults_to_full_quantity(self):
        result = run(CONTRACT, make_inputs())
        assert result["results"]["quantity_shares"] == 150_000

    def test_invalid_ratio_raises(self):
        with pytest.raises(ValueError, match="exercise_scope"):
            run(self._contract(exercise_scope=1.5), make_inputs())
        with pytest.raises(ValueError, match="행사비율"):
            run(self._contract(allocation_ratio=0.0), make_inputs())

    def test_strike_growth_recorded_and_lowers_value(self):
        flat = run(CONTRACT, make_inputs())
        grown = run(self._contract(strike_growth_rate=0.08), make_inputs())
        vi = grown["valuation_inputs"]
        assert vi["strike_growth_rate"] == pytest.approx(0.08)
        assert vi["strike_at_maturity_krw"] > vi["strike_price_krw"]
        assert grown["results"]["unit_value_krw"] < flat["results"]["unit_value_krw"]

    def test_cross_check_passes_with_schedule(self):
        result = run(self._contract(strike_growth_rate=0.08), make_inputs())
        assert result["cross_check"]["passed"] is True
