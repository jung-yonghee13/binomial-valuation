"""KRX 종목 조회·자동완성 검증 (네트워크 없이 목록 모킹)."""
import pytest

from valuation import krx_lookup

LISTING = [
    ("053800", "안랩"),
    ("012510", "더존비즈온"),
    ("030520", "한글과컴퓨터"),
    ("005930", "삼성전자"),
]


@pytest.fixture(autouse=True)
def mock_listing(monkeypatch):
    monkeypatch.setattr(krx_lookup, "_load_listing", lambda: LISTING)
    krx_lookup.clear_cache()
    yield
    krx_lookup.clear_cache()


class TestLookup:
    def test_code_to_name(self):
        assert krx_lookup.code_to_name("053800") == "안랩"
        assert krx_lookup.code_to_name("5930") == "삼성전자"  # zfill 보정
        assert krx_lookup.code_to_name("999999") is None

    def test_name_to_code(self):
        assert krx_lookup.name_to_code("안랩") == "053800"
        assert krx_lookup.name_to_code(" 한글과 컴퓨터 ") == "030520"  # 공백 무시
        assert krx_lookup.name_to_code("없는회사") is None

    def test_is_code(self):
        assert krx_lookup.is_code("053800")
        assert not krx_lookup.is_code("안랩")
        assert not krx_lookup.is_code("5380")


class TestAutofill:
    def test_fills_code_from_name(self):
        assert krx_lookup.autofill("안랩", "") == ("안랩", "053800")

    def test_fills_name_from_code(self):
        assert krx_lookup.autofill("", "012510") == ("더존비즈온", "012510")

    def test_keeps_both_when_present(self):
        assert krx_lookup.autofill("안랩", "999999") == ("안랩", "999999")

    def test_name_typed_into_ticker_column(self):
        # 종목코드 칸에 기업명을 적어도 이름 후보로 해석해 채운다
        assert krx_lookup.autofill("", "삼성전자") == ("삼성전자", "005930")

    def test_unknown_values_are_kept(self):
        assert krx_lookup.autofill("없는회사", "") == ("없는회사", "")
        assert krx_lookup.autofill("", "999999") == ("", "999999")

    def test_lookup_failure_keeps_input(self, monkeypatch):
        def boom():
            raise RuntimeError("network down")
        monkeypatch.setattr(krx_lookup, "_load_listing", boom)
        krx_lookup.clear_cache()
        assert krx_lookup.autofill("안랩", "") == ("안랩", "")
