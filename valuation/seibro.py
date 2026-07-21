"""Seibro(한국예탁결제원 증권정보포털) 채권만기수익률 자동 수집.

[이 파일이 하는 일]
Seibro '채권 > 채권만기수익률' 화면(출처: KIS자산평가)의 데이터 요청을 직접 호출하여
평가기준일의 국고채권 만기별 수익률(3M/6M/9M/1Y/3Y/5Y/10Y/20Y)을 수집한다.

- 무료 공개 조회 화면의 백엔드 요청을 그대로 사용 — API 키·브라우저·토큰 불필요
- 휴일/휴장일이면 직전 영업일로 자동 소급 (최대 lookback 일수)
- 반환 형식은 load_ytm_curve()와 동일하여 spot 부트스트래핑 → 선도이자율
  파이프라인에 그대로 투입된다

참고: KOFIA 채권정보센터는 공식 API가 없고 WAF가 스크립트 접근을 차단하여
자동 수집이 불가함을 진단으로 확인했다 (2026-07-14). Seibro가 동일한 성격의
만기수익률을 무료 제공하므로 이를 기본 수집원으로 사용한다.
"""
from __future__ import annotations

import urllib.request
import xml.etree.ElementTree as ET
from datetime import date as _date
from datetime import timedelta

SEIBRO_URL = "https://seibro.or.kr/websquare/engine/proworks/callServletService.jsp"

# 응답 필드명 -> 만기(년)
_TENOR_FIELDS = [
    ("MONS3_XPIR_PRATE", 0.25),
    ("MONS6_XPIR_PRATE", 0.5),
    ("MONS9_XPIR_PRATE", 0.75),
    ("YY1_XPIR_PRATE", 1.0),
    ("YY3_XPIR_PRATE", 3.0),
    ("YY5_XPIR_PRATE", 5.0),
    ("YY10_XPIR_PRATE", 10.0),
    ("YY20_XPIR_PRATE", 20.0),
]

_PAYLOAD = (
    '<reqParam action="xpirPrateList" task="ksd.safe.bip.cnts.bone.process.BondSecnPTask">'
    '<MENU_NO value="120"/>'
    '<CMM_BTN_ABBR_NM value="total_search,openall,print,hwp,word,pdf,seach,xls,"/>'
    '<W2XPATH value="/IPORTAL/user/bond/BIP_CNTS03030V.xml"/>'
    '<STD_DT value="{std_dt}"/>'
    "</reqParam>"
)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Content-Type": "application/xml; charset=UTF-8",
    "Referer": "https://seibro.or.kr/websquare/control.jsp"
               "?w2xPath=/IPORTAL/user/bond/BIP_CNTS03030V.xml",
}


def _fetch_xml(std_dt: str, timeout: float = 10) -> str:
    """지정일의 채권만기수익률 XML 응답을 받아온다.

    배포 환경(해외 IP)에서는 seibro.or.kr 접근이 차단·지연되므로 timeout을 짧게 잡아
    빨리 실패시키고, 상위(resolve_risk_free)에서 번들 스냅샷으로 폴백하도록 한다.
    """
    payload = _PAYLOAD.format(std_dt=std_dt).encode("utf-8")
    req = urllib.request.Request(SEIBRO_URL, data=payload, headers=_HEADERS, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def _parse_treasury_row(xml_text: str) -> dict | None:
    """응답 XML에서 국고채권 행을 찾아 {필드명: 값} dict로 반환한다."""
    root = ET.fromstring(xml_text)
    for result in root.iter("result"):
        fields = {child.tag: child.get("value") for child in result}
        if fields.get("SECN_SUB_KIND") == "국고채권":
            return fields
    return None


def fetch_treasury_curve(date: str, max_lookback_days: int = 7) -> dict:
    """평가기준일의 국고채권 만기수익률 곡선을 Seibro에서 수집한다.

    date: 'YYYY-MM-DD'. 휴일이면 직전 영업일로 최대 max_lookback_days일 소급.
    반환: load_ytm_curve()와 동일한 형식 {date, source, maturities, yields, ...}
    """
    requested = _date.fromisoformat(str(date))
    row = None
    used = requested
    for back in range(max_lookback_days + 1):
        used = requested - timedelta(days=back)
        row = _parse_treasury_row(_fetch_xml(used.strftime("%Y%m%d")))
        if row:
            break
    if not row:
        raise RuntimeError(
            f"Seibro에서 {date} 및 직전 {max_lookback_days}일 내 국고채권 수익률을 "
            "찾지 못했습니다. 날짜를 확인하거나 수동 곡선 JSON을 사용하세요."
        )

    maturities, yields = [], []
    for field, tenor in _TENOR_FIELDS:
        raw = row.get(field)
        if raw in (None, "", "0", "0.0"):  # 미고시 구간(0)은 제외
            continue
        maturities.append(tenor)
        yields.append(float(raw) / 100.0)

    if len(maturities) < 4:
        raise RuntimeError(f"Seibro 수익률 구간이 {len(maturities)}개뿐입니다: {row}")

    return {
        "date": used.isoformat(),
        "requested_date": str(date),
        "source": "Seibro(한국예탁결제원) 채권만기수익률 — 국고채권, KIS자산평가",
        "maturities": maturities,
        "yields": yields,
    }
