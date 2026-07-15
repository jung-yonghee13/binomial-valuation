"""변동성 산출원 분기 검증: 상장(자기 주가) vs 비상장(피어그룹)."""
import copy

import numpy as np
import pandas as pd
import pytest

from valuation import run_valuation, volatility
from tests.test_run_valuation import BASE_INPUTS, CONTRACT, make_inputs


def _synthetic_prices(sigma, seed, n=245):
    rng = np.random.default_rng(seed)
    daily = sigma / np.sqrt(252)
    lr = rng.normal(0, daily, n)
    p = 10000 * np.exp(np.cumsum(lr))
    idx = pd.bdate_range(end="2026-06-30", periods=n)
    return pd.Series(p, index=idx)


@pytest.fixture()
def mock_prices(monkeypatch):
    # 종목코드별로 알려진 변동성의 합성 시세를 반환
    series = {
        "005930": _synthetic_prices(0.30, 1),   # 상장 기초자산 자기 주가
        "053800": _synthetic_prices(0.28, 2),   # 피어 1
        "012510": _synthetic_prices(0.42, 3),   # 피어 2
    }
    monkeypatch.setattr(volatility, "fetch_close_prices",
                        lambda ticker, start, end: series[ticker])
    return series


def _listed_contract():
    c = copy.deepcopy(CONTRACT)
    c["underlying"]["listing_status"] = "상장"
    c["underlying"]["ticker"] = "005930"
    return c


class TestListedUsesOwnStock:
    def test_listed_uses_own_stock_not_peers(self, mock_prices):
        inputs = make_inputs(volatility="auto")
        # 피어그룹을 넣어도 상장이면 무시되고 자기 주가를 쓴다
        inputs["volatility_estimation"] = {
            "peer_group": [{"name": "안랩", "ticker": "053800"}],
            "lookback_years": 1.0,
        }
        result = run_valuation.run(_listed_contract(), inputs)
        vi = result["valuation_inputs"]["volatility"]
        assert vi["detail"]["own_stock"] is True
        assert len(vi["detail"]["peers"]) == 1
        assert vi["detail"]["peers"][0]["ticker"] == "005930"
        assert "자기 주가" in vi["basis"]
        # 자기 주가(σ≈0.30)로 산출, 피어(0.28)가 아님
        assert vi["value"] == pytest.approx(0.30, abs=0.03)

    def test_listed_without_peer_group_works(self, mock_prices):
        # 상장이면 피어그룹이 없어도 평가된다
        inputs = make_inputs(volatility="auto")
        inputs.pop("volatility_estimation", None)
        result = run_valuation.run(_listed_contract(), inputs)
        assert result["valuation_inputs"]["volatility"]["detail"]["own_stock"] is True


class TestUnlistedUsesPeerGroup:
    def test_unlisted_uses_peer_group(self, mock_prices):
        inputs = make_inputs(volatility="auto")
        inputs["volatility_estimation"] = {
            "peer_group": [
                {"name": "안랩", "ticker": "053800"},
                {"name": "더존비즈온", "ticker": "012510"},
            ],
            "lookback_years": 1.0,
        }
        result = run_valuation.run(CONTRACT, inputs)  # 비상장
        vi = result["valuation_inputs"]["volatility"]
        assert not vi["detail"].get("own_stock")
        assert len(vi["detail"]["peers"]) == 2
        # 피어 평균 (0.28, 0.42) ≈ 0.35
        assert vi["value"] == pytest.approx(0.35, abs=0.04)

    def test_unlisted_without_peer_group_raises(self):
        inputs = make_inputs(volatility="auto")
        inputs.pop("volatility_estimation", None)
        with pytest.raises(ValueError, match="피어그룹"):
            run_valuation.run(CONTRACT, inputs)


class TestManualVolatilityUnaffected:
    def test_manual_value_ignores_listing(self):
        # 변동성을 직접 입력하면 상장/비상장과 무관하게 그 값을 쓴다
        result = run_valuation.run(_listed_contract(), make_inputs(volatility=0.5))
        assert result["valuation_inputs"]["volatility"]["value"] == 0.5
        assert result["valuation_inputs"]["volatility"]["detail"] is None
