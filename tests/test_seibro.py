"""Seibro 수집 모듈 검증 (네트워크 없이 응답 모킹)."""
import pytest

from valuation import seibro

TREASURY_XML = """<?xml version="1.0" encoding="UTF-8" ?>
<vector result="2">
  <data vectorkey="0" type="Document">
    <result>
      <STD_DT value="20260630"/><SECN_KIND value="국채"/><SECN_SUB_KIND value="국고채권"/>
      <MONS3_XPIR_PRATE value="2.79"/><MONS6_XPIR_PRATE value="3.02"/>
      <MONS9_XPIR_PRATE value="3.27"/><YY1_XPIR_PRATE value="3.35"/>
      <YY3_XPIR_PRATE value="3.88"/><YY5_XPIR_PRATE value="4.05"/>
      <YY10_XPIR_PRATE value="4.20"/><YY20_XPIR_PRATE value="4.25"/>
    </result>
  </data>
  <data vectorkey="1" type="Document">
    <result>
      <STD_DT value="20260630"/><SECN_KIND value="국채"/><SECN_SUB_KIND value="국민주택1종"/>
      <MONS3_XPIR_PRATE value="2.80"/><MONS6_XPIR_PRATE value="3.05"/>
      <MONS9_XPIR_PRATE value="3.30"/><YY1_XPIR_PRATE value="3.40"/>
      <YY3_XPIR_PRATE value="3.90"/><YY5_XPIR_PRATE value="4.28"/>
      <YY10_XPIR_PRATE value="0"/><YY20_XPIR_PRATE value="0"/>
    </result>
  </data>
</vector>"""

EMPTY_XML = '<?xml version="1.0" encoding="UTF-8" ?><vector result="0"></vector>'


class TestFetchTreasuryCurve:
    def test_parses_treasury_row(self, monkeypatch):
        monkeypatch.setattr(seibro, "_fetch_xml", lambda dt: TREASURY_XML)
        curve = seibro.fetch_treasury_curve("2026-06-30")
        assert curve["maturities"] == [0.25, 0.5, 0.75, 1.0, 3.0, 5.0, 10.0, 20.0]
        assert curve["yields"][0] == pytest.approx(0.0279)
        assert curve["yields"][-1] == pytest.approx(0.0425)
        assert "국고채권" in curve["source"]

    def test_holiday_falls_back_to_previous_business_day(self, monkeypatch):
        calls = []

        def fake_fetch(dt):
            calls.append(dt)
            return EMPTY_XML if dt in ("20260712", "20260711") else TREASURY_XML

        monkeypatch.setattr(seibro, "_fetch_xml", fake_fetch)
        curve = seibro.fetch_treasury_curve("2026-07-12")  # 일요일 가정
        assert calls == ["20260712", "20260711", "20260710"]
        assert curve["date"] == "2026-07-10"
        assert curve["requested_date"] == "2026-07-12"

    def test_zero_yields_are_dropped(self, monkeypatch):
        # 국민주택1종처럼 미고시 구간이 0으로 오는 행 대응 (국고채권 행 자체에 0이 있어도 제외)
        xml = TREASURY_XML.replace('<YY20_XPIR_PRATE value="4.25"/>', '<YY20_XPIR_PRATE value="0"/>')
        monkeypatch.setattr(seibro, "_fetch_xml", lambda dt: xml)
        curve = seibro.fetch_treasury_curve("2026-06-30")
        assert 20.0 not in curve["maturities"]

    def test_exhausted_lookback_raises(self, monkeypatch):
        monkeypatch.setattr(seibro, "_fetch_xml", lambda dt: EMPTY_XML)
        with pytest.raises(RuntimeError, match="Seibro"):
            seibro.fetch_treasury_curve("2026-06-30", max_lookback_days=3)

    def test_curve_feeds_bootstrap(self, monkeypatch):
        from valuation.risk_free import spot_rate, step_forward_rates

        monkeypatch.setattr(seibro, "_fetch_xml", lambda dt: TREASURY_XML)
        curve = seibro.fetch_treasury_curve("2026-06-30")
        r = spot_rate(curve["maturities"], curve["yields"], 2.7)
        assert 0.0 < r < 0.1
        forwards = step_forward_rates(curve["maturities"], curve["yields"], 7 / 365, 100)
        assert len(forwards) == 100
