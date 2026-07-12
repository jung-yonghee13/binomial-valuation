"""국고채 수익률 기반 무위험이자율(spot rate) 산출.

만기별 국고채 수익률(YTM, 액면수익률로 가정) 곡선에서 부트스트래핑으로
spot rate 곡선을 산출하고, 평가대상의 잔존만기에 대응하는 spot rate를
보간하여 연속복리 기준으로 반환한다 (트리 엔진의 복리 일관성 원칙과 정합).

데이터 원천: 금융투자협회 채권정보센터 (https://www.kofiabond.or.kr)
- 공식 REST API가 없어 자동 수집(fetch_kofia_ytm)은 아직 미구현이다.
- 구현 전까지는 사이트에서 평가기준일의 국고채 수익률을 확인하여
  JSON 파일로 작성하고 load_ytm_curve()로 투입한다.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

COUPON_FREQ = 2  # 국고채 반기 이표 가정


def bootstrap_spot_curve(
    maturities, par_yields, freq: int = COUPON_FREQ
) -> tuple[np.ndarray, np.ndarray]:
    """액면수익률(par yield) 곡선에서 연속복리 spot rate 곡선을 부트스트래핑한다.

    단순화 가정: 이표는 연 freq회 지급, 그리드 사이 액면수익률은 선형 보간.
    수익률은 소수 표기(0.03 = 3%). 반환: (그리드 만기, 연속복리 spot rate).
    """
    m = np.asarray(maturities, dtype=float)
    y = np.asarray(par_yields, dtype=float)
    if len(m) != len(y) or len(m) == 0:
        raise ValueError("만기와 수익률 배열의 길이가 일치해야 합니다.")
    if np.any(m <= 0):
        raise ValueError("만기는 양수여야 합니다.")
    if np.any(np.diff(m) <= 0):
        raise ValueError("만기는 오름차순으로 정렬되어야 합니다.")
    if np.any(y >= 1.0):
        raise ValueError("수익률은 소수로 표기해야 합니다 (예: 3% -> 0.03).")

    grid = np.arange(1, int(round(m[-1] * freq)) + 1) / freq
    par = np.interp(grid, m, y)

    dfs = np.empty(len(grid))
    for i, rate in enumerate(par):
        coupon = rate / freq
        pv_coupons = float((coupon * dfs[:i]).sum())
        dfs[i] = (1.0 - pv_coupons) / (1.0 + coupon)

    spots = -np.log(dfs) / grid
    return grid, spots


def spot_rate(
    maturities, par_yields, target_maturity: float, freq: int = COUPON_FREQ
) -> float:
    """잔존만기에 대응하는 연속복리 spot rate (그리드 사이 선형 보간).

    target_maturity가 그리드 범위를 벗어나면 가장 가까운 끝 값을 사용한다.
    """
    if target_maturity <= 0:
        raise ValueError("잔존만기는 양수여야 합니다.")
    grid, spots = bootstrap_spot_curve(maturities, par_yields, freq)
    return float(np.interp(target_maturity, grid, spots))


def load_ytm_curve(path) -> dict:
    """JSON 파일에서 국고채 수익률 곡선을 로드한다.

    형식: {"date": "YYYY-MM-DD", "maturities": [...], "yields": [...], ...}
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    for key in ("maturities", "yields"):
        if key not in data:
            raise ValueError(f"수익률 곡선 파일에 '{key}' 항목이 없습니다: {path}")
    if len(data["maturities"]) != len(data["yields"]):
        raise ValueError("maturities와 yields의 길이가 일치해야 합니다.")
    return data


def fetch_kofia_ytm(date) -> dict:
    """KOFIA 채권정보센터에서 평가기준일의 국고채 수익률을 수집한다 (미구현).

    KOFIA BIS는 공식 REST API를 제공하지 않아 페이지 데이터 요청 분석이 필요하다.
    구현 전까지는 수동으로 수익률 곡선 JSON을 작성하여 load_ytm_curve()로 투입한다.
    """
    raise NotImplementedError(
        "KOFIA 자동 수집은 아직 구현되지 않았습니다. "
        "https://www.kofiabond.or.kr 에서 평가기준일 국고채 수익률을 확인하여 "
        "수익률 곡선 JSON 파일을 작성한 뒤 입력 파일의 "
        "risk_free_estimation.ytm_curve_file 로 지정하세요."
    )
