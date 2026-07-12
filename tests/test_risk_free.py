"""무위험이자율 산출 검증: 부트스트래핑, 보간, 입력 검증."""
import numpy as np
import pytest

from valuation.risk_free import bootstrap_spot_curve, load_ytm_curve, spot_rate

MATURITIES = [0.5, 1.0, 2.0, 3.0, 5.0, 10.0]


class TestBootstrap:
    def test_flat_par_curve_gives_flat_spot_curve(self):
        # 평평한 액면수익률 곡선 -> spot도 동일 수준 (연속복리 환산치)
        y = 0.03
        grid, spots = bootstrap_spot_curve(MATURITIES, [y] * len(MATURITIES))
        expected = 2 * np.log(1 + y / 2)  # 반기복리 -> 연속복리
        assert np.allclose(spots, expected, atol=1e-10)

    def test_upward_curve_spot_above_par_at_long_end(self):
        # 우상향 곡선에서는 장기 spot이 액면수익률보다 높다
        yields = [0.02, 0.022, 0.025, 0.027, 0.029, 0.032]
        grid, spots = bootstrap_spot_curve(MATURITIES, yields)
        assert spots[-1] > 0.032

    def test_invalid_inputs_raise(self):
        with pytest.raises(ValueError):
            bootstrap_spot_curve([1.0, 2.0], [0.03])  # 길이 불일치
        with pytest.raises(ValueError):
            bootstrap_spot_curve([2.0, 1.0], [0.03, 0.03])  # 정렬 위반
        with pytest.raises(ValueError):
            bootstrap_spot_curve([1.0, 2.0], [3.0, 3.0])  # 퍼센트 표기 오입력


class TestSpotRate:
    def test_interpolates_between_grid_points(self):
        yields = [0.02, 0.022, 0.025, 0.027, 0.029, 0.032]
        r_2y = spot_rate(MATURITIES, yields, 2.0)
        r_3y = spot_rate(MATURITIES, yields, 3.0)
        r_between = spot_rate(MATURITIES, yields, 2.5)
        assert min(r_2y, r_3y) <= r_between <= max(r_2y, r_3y)

    def test_invalid_maturity_raises(self):
        with pytest.raises(ValueError):
            spot_rate(MATURITIES, [0.03] * len(MATURITIES), -1.0)


class TestLoadCurve:
    def test_load_sample_curve(self):
        curve = load_ytm_curve("data/sample_ytm_curve.json")
        assert len(curve["maturities"]) == len(curve["yields"])
        rate = spot_rate(curve["maturities"], curve["yields"], 2.7)
        assert 0.0 < rate < 0.1
