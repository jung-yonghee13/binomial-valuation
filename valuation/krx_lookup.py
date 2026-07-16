"""KRX 상장종목 조회 — 기업명 ↔ 종목코드 상호 변환.

[이 파일이 하는 일]
피어그룹을 입력할 때 기업명만 적으면 종목코드를, 종목코드만 적으면 기업명을
자동으로 채워 넣기 위한 조회 기능이다. KRX 전체 상장종목 목록을
FinanceDataReader로 한 번 받아 캐시하고, 이름↔코드 매핑을 만든다.

- name_to_code("안랩") -> "053800"
- code_to_name("053800") -> "안랩"
- 찾지 못하면 None을 반환한다 (호출 측에서 원래 값 유지).
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

# (테스트에서 교체 가능한) 상장목록 로더 — (종목코드, 기업명) 목록을 반환한다
_listing_cache: dict[str, dict] | None = None

# 라이브 수집 실패 시 폴백용 스냅샷 (배포 서버에서 KRX가 해외 IP를 차단하는 경우 대비)
_FALLBACK_CSV = Path(__file__).resolve().parent.parent / "data" / "krx_listing.csv"


def _load_listing_live() -> "list[tuple[str, str]]":
    """KRX 전체 상장종목의 (종목코드, 기업명) 목록을 실시간으로 받아온다."""
    try:
        import FinanceDataReader as fdr
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "종목 조회에는 FinanceDataReader가 필요합니다: pip install finance-datareader"
        ) from exc

    df = fdr.StockListing("KRX")
    # FinanceDataReader 버전에 따라 컬럼명이 Code/Symbol, Name 등으로 다를 수 있다
    code_col = next((c for c in ("Code", "Symbol") if c in df.columns), None)
    name_col = next((c for c in ("Name", "Korean Name") if c in df.columns), None)
    if code_col is None or name_col is None:
        raise RuntimeError(f"상장목록 컬럼을 찾지 못했습니다: {list(df.columns)}")
    return [
        (str(row[code_col]).zfill(6), str(row[name_col]).strip())
        for _, row in df.iterrows()
        if row[code_col] is not None and row[name_col]
    ]


def _load_listing_snapshot() -> "list[tuple[str, str]]":
    """저장소에 동봉된 상장목록 스냅샷(data/krx_listing.csv)을 읽는다."""
    with open(_FALLBACK_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [(row["code"].zfill(6), row["name"].strip()) for row in reader]


def _load_listing() -> "list[tuple[str, str]]":
    """상장목록 확보: 동봉 스냅샷을 우선 사용한다 (즉시 응답·결정론적).

    실시간 수집(fdr.StockListing)은 배포 서버(해외 IP)에서 차단되거나 수십 초씩
    지연될 수 있어 UI 자동완성 용도로는 부적합하다. 스냅샷 파일이 없을 때만
    실시간 수집을 시도한다. (신규 상장사 반영이 필요하면 스냅샷을 재생성:
    python -c "from valuation import krx_lookup, csv 사용 예는 저장소 이력 참조")
    """
    try:
        listing = _load_listing_snapshot()
        if listing:
            return listing
    except Exception:
        pass  # 스냅샷 누락·손상 → 실시간 수집 시도
    return _load_listing_live()


def _normalize(name: str) -> str:
    """이름 비교용 정규화 — 공백·괄호 표기 차이를 흡수한다."""
    return re.sub(r"\s+", "", str(name)).lower()


def _build_index() -> dict[str, dict]:
    """이름→코드, 코드→이름 매핑을 만들어 캐시한다."""
    global _listing_cache
    if _listing_cache is None:
        by_code: dict[str, str] = {}
        by_name: dict[str, str] = {}
        for code, name in _load_listing():
            by_code.setdefault(code, name)
            by_name.setdefault(_normalize(name), code)
        _listing_cache = {"by_code": by_code, "by_name": by_name}
    return _listing_cache


def clear_cache() -> None:
    """캐시를 비운다 (테스트·강제 갱신용)."""
    global _listing_cache
    _listing_cache = None


def is_code(text: str) -> bool:
    """입력이 6자리 종목코드 형태인지 판별한다."""
    return bool(re.fullmatch(r"\d{6}", str(text).strip()))


def code_to_name(code: str) -> str | None:
    """종목코드로 기업명을 조회한다 (없으면 None)."""
    return _build_index()["by_code"].get(str(code).strip().zfill(6))


def name_to_code(name: str) -> str | None:
    """기업명으로 종목코드를 조회한다 (없으면 None)."""
    return _build_index()["by_name"].get(_normalize(name))


def autofill(name: str, ticker: str) -> tuple[str, str]:
    """한쪽만 채워진 (기업명, 종목코드)에서 비어 있는 쪽을 채운다.

    - 기업명만 있으면: 코드 조회
    - 종목코드만 있으면: 기업명 조회
    - 둘 다 있으면: 그대로 둔다 (사용자 입력 존중)
    - 조회 실패나 네트워크 오류: 원래 값 유지 (예외를 던지지 않는다)
    반환: (기업명, 종목코드)
    """
    def _clean(x) -> str:
        if x is None:
            return ""
        s = str(x).strip()
        return "" if s.lower() in ("nan", "none") else s

    name = _clean(name)
    ticker = _clean(ticker)
    # 종목코드 칸에 기업명을 적은 경우도 대응: 코드가 아니면 이름 후보로 본다
    if ticker and not is_code(ticker) and not name:
        name, ticker = ticker, ""

    try:
        if name and not ticker:
            code = name_to_code(name)
            if code:
                ticker = code
        elif ticker and not name:
            found = code_to_name(ticker)
            if found:
                name = found
        elif name and ticker:
            # 기존 행의 기업명을 다른 회사로 바꾼 경우: 이름이 상장목록과 일치하는데
            # 코드가 다르면 이름 기준으로 코드를 맞춘다 (이름이 목록에 없으면
            # 사용자 지정 표기로 보고 그대로 둔다)
            code = name_to_code(name)
            if code and code != ticker.zfill(6):
                ticker = code
    except Exception:
        pass  # 조회 실패 시 입력값을 그대로 둔다
    return name, ticker
