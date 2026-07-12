"""국고채 수익률 기반 무위험이자율(spot rate) 산출.

[이 파일이 하는 일]
KOFIA 채권정보센터 등에서 확인한 "만기별 국고채 수익률(YTM)"에서
평가에 실제로 써야 하는 "spot rate(현물이자율)"를 만들어 낸다.

[왜 YTM을 그대로 쓰지 않고 spot rate를 쓰는가]
고시되는 국고채 수익률(YTM)은 "중간에 이자를 받는 이표채"의 수익률이라
서로 다른 시점의 현금흐름이 섞여 있다. 옵션 평가에는 "만기에 한 번만
현금흐름이 있는 순수한 할인율" = spot rate가 이론적으로 맞다.

[산출 절차]
1. 만기별 YTM 곡선 확보 (수동 JSON 입력 또는 추후 KOFIA 자동 수집)
2. 부트스트래핑: 짧은 만기부터 차례로 "이표의 현재가치를 걷어내고"
   순수 할인계수(discount factor)를 역산한다
3. 평가대상의 잔존만기에 해당하는 spot rate를 보간으로 선택
4. 연속복리로 환산해서 반환 → 트리 엔진(binomial.py)의 복리 기준과 일치

주의: 수익률은 소수로 표기한다 (3% -> 0.03). 퍼센트 숫자를 넣으면 예외 발생.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

COUPON_FREQ = 2  # 국고채는 이자를 연 2회(반기) 지급한다고 가정


def bootstrap_spot_curve(
    maturities, par_yields, freq: int = COUPON_FREQ
) -> tuple[np.ndarray, np.ndarray]:
    """액면수익률(par yield) 곡선에서 연속복리 spot rate 곡선을 부트스트래핑한다.

    [부트스트래핑 원리]
    액면수익률 y의 채권은 "가격 = 액면가"이므로 다음 등식이 성립한다:
        1 = (이표 c × 각 시점 할인계수의 합) + (1 + c) × 만기 할인계수
    짧은 만기부터 풀면 앞선 할인계수들은 이미 알고 있으므로,
        만기 할인계수 = (1 - c × 앞선 할인계수 합) / (1 + c)
    로 하나씩 역산할 수 있다. 이것이 아래 for문이 하는 일이다.

    반환: (그리드 만기 배열, 연속복리 spot rate 배열)
    """
    m = np.asarray(maturities, dtype=float)
    y = np.asarray(par_yields, dtype=float)
    # ── 입력 검증 ──
    if len(m) != len(y) or len(m) == 0:
        raise ValueError("만기와 수익률 배열의 길이가 일치해야 합니다.")
    if np.any(m <= 0):
        raise ValueError("만기는 양수여야 합니다.")
    if np.any(np.diff(m) <= 0):
        raise ValueError("만기는 오름차순으로 정렬되어야 합니다.")
    if np.any(y >= 1.0):
        raise ValueError("수익률은 소수로 표기해야 합니다 (예: 3% -> 0.03).")

    # 반기(0.5년) 간격 그리드를 만들고, 고시 만기 사이는 선형 보간으로 채운다
    grid = np.arange(1, int(round(m[-1] * freq)) + 1) / freq
    par = np.interp(grid, m, y)

    # 짧은 만기부터 순서대로 할인계수를 역산 (부트스트래핑 본체)
    dfs = np.empty(len(grid))
    for i, rate in enumerate(par):
        coupon = rate / freq                          # 반기 이표
        pv_coupons = float((coupon * dfs[:i]).sum())  # 앞선 시점 이표들의 현재가치
        dfs[i] = (1.0 - pv_coupons) / (1.0 + coupon)  # 만기 할인계수 역산

    # 할인계수 -> 연속복리 spot rate: df = exp(-r·t) 이므로 r = -ln(df)/t
    spots = -np.log(dfs) / grid
    return grid, spots


def spot_rate(
    maturities, par_yields, target_maturity: float, freq: int = COUPON_FREQ
) -> float:
    """평가대상의 잔존만기에 대응하는 연속복리 spot rate를 반환한다.

    그리드 사이 값은 선형 보간하고, 그리드 범위를 벗어나면
    가장 가까운 끝 값을 사용한다 (np.interp의 기본 동작).
    """
    if target_maturity <= 0:
        raise ValueError("잔존만기는 양수여야 합니다.")
    grid, spots = bootstrap_spot_curve(maturities, par_yields, freq)
    return float(np.interp(target_maturity, grid, spots))


def load_ytm_curve(path) -> dict:
    """JSON 파일에서 국고채 수익률 곡선을 로드한다.

    파일 형식 (data/sample_ytm_curve.json 참조):
        {"date": "YYYY-MM-DD", "maturities": [0.25, 0.5, ...], "yields": [0.0245, ...]}
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
