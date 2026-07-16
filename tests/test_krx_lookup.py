"""KRX 종목 조회·자동완성 검증 (네트워크 없이 목록 모킹)."""
import pytest

from valuation import krx_lookup

# autouse 픽스처가 _load_listing을 목킹하기 전에 원본을 보관 (폴백 경로 검증용)
_REAL_LOAD_LISTING = krx_lookup._load_listing

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

    def test_name_wins_when_both_present_but_inconsistent(self):
        # 기존 행의 기업명을 다른 회사로 바꾸면 코드가 이름을 따라간다
        assert krx_lookup.autofill("삼성전자", "030520") == ("삼성전자", "005930")
        assert krx_lookup.autofill("안랩", "999999") == ("안랩", "053800")

    def test_consistent_pair_is_untouched(self):
        assert krx_lookup.autofill("안랩", "053800") == ("안랩", "053800")

    def test_custom_name_with_valid_code_is_kept(self):
        # 목록에 없는 이름(사용자 지정 표기)은 코드가 있어도 건드리지 않는다
        assert krx_lookup.autofill("피어후보(비교용)", "053800") == ("피어후보(비교용)", "053800")

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

    def test_nan_like_inputs_are_cleaned(self):
        # 편집 표에서 NaN/None이 문자열로 넘어와도 안전하게 처리
        assert krx_lookup.autofill(float("nan"), "053800") == ("안랩", "053800")
        assert krx_lookup.autofill(None, None) == ("", "")
        assert krx_lookup.autofill("nan", "012510") == ("더존비즈온", "012510")


class TestSnapshotFallback:
    def test_live_failure_falls_back_to_snapshot(self, monkeypatch):
        # 실시간 수집이 죽어도 동봉 스냅샷으로 조회가 계속 된다 (배포 서버 KRX 차단 대비)
        def boom():
            raise RuntimeError("blocked")
        monkeypatch.setattr(krx_lookup, "_load_listing_live", boom)
        monkeypatch.setattr(krx_lookup, "_load_listing", _REAL_LOAD_LISTING)
        krx_lookup.clear_cache()
        # 스냅샷은 실제 KRX 목록이므로 삼성전자가 반드시 있다
        assert krx_lookup.name_to_code("삼성전자") == "005930"

    def test_snapshot_file_is_valid(self):
        listing = krx_lookup._load_listing_snapshot()
        assert len(listing) > 2000
        assert all(len(code) == 6 and code.isdigit() for code, _ in listing[:50])
