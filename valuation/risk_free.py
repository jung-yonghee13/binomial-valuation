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


def step_forward_rates(
    maturities, par_yields, step_years: float, steps: int, freq: int = COUPON_FREQ
) -> np.ndarray:
    """트리 스텝별 선도이자율(단리)을 산출한다 — 기간구조 반영 트리용.

    [왜 선도이자율인가]
    무위험이자율을 하나의 값으로 고정하지 않고, 수익률곡선의 기간구조를
    트리의 매 스텝에 반영하는 실무 방식이다. 스텝 i의 선도이자율은
    "시점 t_{i-1}에서 t_i까지 한 구간에 적용되는 시장이 내재한 이자율"로,
    할인계수(DF)의 비율에서 도출된다:

        1 + f_i = DF(t_{i-1}) / DF(t_i),   DF(t) = exp(-spot(t) · t)

    반환: 길이 steps의 단리 선도이자율 배열 (스텝당).
    트리에서 스텝별 위험중립확률·할인에 일관되게 사용한다.
    """
    if step_years <= 0 or steps < 1:
        raise ValueError("step_years는 양수, steps는 1 이상이어야 합니다.")

    grid, spots = bootstrap_spot_curve(maturities, par_yields, freq)

    # 각 스텝 경계 시점의 연속복리 spot rate (그리드 보간, 범위 밖은 끝값)
    t = np.arange(steps + 1) * step_years  # t_0=0, t_1, ..., t_steps
    spot_t = np.interp(t, grid, spots)

    # 할인계수 DF(t) = exp(-spot·t); DF(0) = 1
    df = np.exp(-spot_t * t)

    # 선도이자율(단리): 1 + f_i = DF(t_{i-1}) / DF(t_i)
    forwards = df[:-1] / df[1:] - 1.0
    return forwards


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
    """KOFIA 국고채 수익률 자동 수집 — 파이썬 직접 수집은 지원하지 않는다.

    KOFIA BIS는 공식 REST API가 없다. 자동 수집은 에이전트가 Chrome 브라우저로
    페이지를 열어 값을 읽는 방식으로 수행한다
    (.claude/skills/valuation-report/SKILL.md 의 2-B-a 절차 참조).
    에이전트가 수집 결과를 ytm_curve JSON으로 저장하면 load_ytm_curve()로 투입된다.
    """
    raise NotImplementedError(
        "KOFIA 수익률은 브라우저 수집 절차로 가져옵니다 (SKILL.md 2-B-a). "
        "수집된 곡선 JSON을 입력 파일의 risk_free_estimation.ytm_curve_file 로 "
        "지정하세요. (수동 입력 폴백도 동일 형식)"
    )
