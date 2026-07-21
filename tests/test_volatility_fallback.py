"""FDR 피어 주가 폴백·부분실패 허용 검증 (SEIBRO 폴백 패턴 이식분).

네트워크 없이 monkeypatch로 실패를 강제하고, 정상 경로 수치 불변 + 실패 시
스냅샷 폴백/명확한 실패가 나오는지 확인한다.
"""
import copy

import numpy as np
import pandas as pd
import pytest

from valuation import run_valuation, volatility
from valuation.volatility import PriceFetchError, peer_group_volatility
from tests.test_run_valuation import CONTRACT, make_inputs


def _synthetic_prices(sigma, seed, n=245):
    rng = np.random.default_rng(seed)
    daily = sigma / np.sqrt(252)
    lr = rng.normal(0, daily, n)
    p = 10000 * np.exp(np.cumsum(lr))
    idx = pd.bdate_range(end="2026-06-30", periods=n)
    return pd.Series(p, index=idx)


PEER_GROUP = [
    {"name": "안랩", "ticker": "053800"},
    {"name": "더존비즈온", "ticker": "012510"},
    {"name": "한글과컴퓨터", "ticker": "030520"},
]


class TestFetchWrapsNetworkError:
    def test_raw_exception_wrapped_as_price_fetch_error(self, monkeypatch):
        import FinanceDataReader as fdr

        def boom(*a, **k):
            raise ConnectionError("HTTPSConnectionPool: Read timed out")

        monkeypatch.setattr(fdr, "DataReader", boom)
        with pytest.raises(PriceFetchError, match="시세 수집에 실패"):
            volatility.fetch_close_prices("053800", "2025-06-30", "2026-06-30")


class TestPeerPartialFailure:
    def test_one_peer_fails_others_proceed(self, monkeypatch):
        series = {
            "053800": _synthetic_prices(0.28, 2),
            "012510": _synthetic_prices(0.42, 3),
            # 030520 없음 → KeyError를 PriceFetchError로 바꿔주는 wrapper 대신
        }

        def fake(ticker, start, end):
            if ticker not in series:
                raise PriceFetchError(f"종목 {ticker} 차단")
            return series[ticker]

        monkeypatch.setattr(volatility, "fetch_close_prices", fake)
        detail = peer_group_volatility(PEER_GROUP, "2026-06-30")
        # 2개 성공, 1개 실패 → 성공분만으로 평균, 실패는 기록
        assert len(detail["peers"]) == 2
        assert len(detail["failed_peers"]) == 1
        assert detail["failed_peers"][0]["ticker"] == "030520"
        assert detail["mean_volatility"] == pytest.approx(0.35, abs=0.05)

    def test_too_many_failures_raises(self, monkeypatch):
        def fake(ticker, start, end):
            raise PriceFetchError(f"종목 {ticker} 차단")

        monkeypatch.setattr(volatility, "fetch_close_prices", fake)
        with pytest.raises(PriceFetchError, match="피어그룹 시세 수집 실패"):
            peer_group_volatility(PEER_GROUP, "2026-06-30")


class TestResolveVolatilityFallback:
    def test_peer_block_falls_back_to_snapshot(self, monkeypatch):
        # 전 피어 차단 → 번들 스냅샷 폴백 + 투명 표기 + fallback_used
        def boom(ticker, start, end):
            raise PriceFetchError(f"종목 {ticker} 차단(해외 IP)")

        monkeypatch.setattr(volatility, "fetch_close_prices", boom)
        inputs = make_inputs(volatility="auto")
        inputs["volatility_estimation"] = {"peer_group": PEER_GROUP, "lookback_years": 1.0}
        vol = run_valuation.resolve_volatility(inputs, CONTRACT)
        assert vol["fallback_used"] is True
        assert "스냅샷" in vol["basis"]
        assert "FDR 실시간 수집 실패" in vol["basis"]
        assert vol["detail"]["fallback_used"] is True
        assert vol["value"] > 0
        assert vol["detail"]["snapshot_date"]

    def test_listed_own_stock_falls_back_to_snapshot(self, monkeypatch):
        def boom(*a, **k):
            raise PriceFetchError("자기 주가 차단")

        monkeypatch.setattr(volatility, "fetch_close_prices", boom)
        listed = copy.deepcopy(CONTRACT)
        listed["underlying"]["listing_status"] = "상장"
        listed["underlying"]["ticker"] = "005930"
        inputs = make_inputs(volatility="auto")
        vol = run_valuation.resolve_volatility(inputs, listed)
        assert vol["fallback_used"] is True
        assert vol["value"] > 0

    def test_full_run_succeeds_under_fdr_block(self, monkeypatch):
        # 폴백이 실제 평가 파이프라인을 끝까지 통과시키는지 (조용한 실패 아님)
        def boom(ticker, start, end):
            raise PriceFetchError("차단")

        monkeypatch.setattr(volatility, "fetch_close_prices", boom)
        inputs = make_inputs(volatility="auto")
        inputs["volatility_estimation"] = {"peer_group": PEER_GROUP, "lookback_years": 1.0}
        result = run_valuation.run(CONTRACT, inputs)
        assert result["results"]["unit_value_krw"] > 0
        assert result["valuation_inputs"]["volatility"]["fallback_used"] is True


class TestRequiredKeys:
    def test_missing_strike_raises_clear_message(self):
        inputs = make_inputs()
        del inputs["inputs"]["strike_price_krw"]
        with pytest.raises(ValueError, match="strike_price_krw"):
            run_valuation.run(CONTRACT, inputs)

    def test_missing_maturity_raises_clear_message(self):
        inputs = make_inputs()
        del inputs["inputs"]["maturity_date"]
        with pytest.raises(ValueError, match="maturity_date"):
            run_valuation.run(CONTRACT, inputs)
