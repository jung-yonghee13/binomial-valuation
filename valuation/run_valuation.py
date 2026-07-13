"""평가 실행 진입점 — 전체 파이프라인을 한 번에 돌리는 파일.

[이 파일이 하는 일]
계약정보(JSON)와 평가 주요변수(JSON) 두 파일을 입력받아 아래 순서로 실행한다.

  1) 입력 해석  : 변동성·무위험이자율이 "auto"면 자동 산출, 숫자면 그대로 사용
  2) 본 평가    : CRR 이항모형으로 콜옵션 1주당 가치 × 대상주식수량 = 총 평가액
  3) 교차검증   : 몬테카를로로 독립 계산 → 95% 신뢰구간 합격/불합격 판정
  4) 민감도 분석: 주요변수를 흔들었을 때 평가액이 얼마나 변하는지
  5) 결과 저장  : 모든 산출 내역을 결과 JSON으로 저장
                  → 이 JSON이 보고서 생성(valuation/report.py)의 입력이 된다

[사용 예 — 터미널에서]
    python -m valuation.run_valuation --contract data/sample_contract.json \\
        --inputs data/my_inputs.json --output-dir results
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path

import numpy as np

from valuation import monte_carlo, payoffs, risk_free, volatility
from valuation.binomial import BinomialParams, price, price_with_curve

DAYS_PER_YEAR = 365.0  # 잔존만기 연 환산 기준 (ACT/365: 실제 일수 ÷ 365)


def load_json(path) -> dict:
    """UTF-8 JSON 파일을 읽어 dict로 반환한다."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def years_between(start: str, end: str) -> float:
    """두 날짜 사이 기간을 연 단위로 환산한다 (예: 평가기준일 ~ 만기일)."""
    d0 = date.fromisoformat(str(start))
    d1 = date.fromisoformat(str(end))
    days = (d1 - d0).days
    if days <= 0:
        raise ValueError(f"만기일({end})이 평가기준일({start}) 이후여야 합니다.")
    return days / DAYS_PER_YEAR


def resolve_volatility(inputs: dict) -> dict:
    """변동성 입력을 해석한다.

    - 숫자면: 사용자가 직접 추정해 넣은 값으로 그대로 사용
    - "auto"면: 피어그룹 주가를 수집해 역사적 변동성 평균을 자동 산출
    반환 dict에는 값과 함께 산출 근거(basis)와 상세 내역(detail)이 담긴다.
    """
    value = inputs["inputs"]["volatility"]
    if isinstance(value, (int, float)):
        return {"value": float(value), "basis": "사용자 직접 입력", "detail": None}

    if value != "auto":
        raise ValueError("volatility는 숫자 또는 'auto'여야 합니다.")

    est = inputs.get("volatility_estimation", {})
    detail = volatility.peer_group_volatility(
        peer_group=est["peer_group"],
        valuation_date=inputs["inputs"]["valuation_date"],
        lookback_years=est.get("lookback_years", 1.0),
        trading_days=est.get("annualization_factor", volatility.TRADING_DAYS),
    )
    return {
        "value": detail["mean_volatility"],
        "basis": "피어그룹 역사적 변동성 산술평균 (자동 산출)",
        "detail": detail,
    }


def resolve_risk_free(inputs: dict, maturity_years: float) -> dict:
    """무위험이자율 입력을 해석한다.

    - 숫자면: 연속복리 기준 값으로 간주하고 그대로 사용
    - "auto"면: 국고채 수익률 곡선에서 잔존만기 대응 spot rate를 산출
      (곡선은 ytm_curve_file로 지정한 JSON에서 로드, 없으면 KOFIA 수집 시도)
    """
    value = inputs["inputs"]["risk_free_rate"]
    if isinstance(value, (int, float)):
        return {"value": float(value), "basis": "사용자 직접 입력 (연속복리 가정)", "detail": None}

    if value != "auto":
        raise ValueError("risk_free_rate는 숫자 또는 'auto'여야 합니다.")

    est = inputs.get("risk_free_estimation", {})
    curve_file = est.get("ytm_curve_file")
    if curve_file:
        curve = risk_free.load_ytm_curve(curve_file)
    else:
        # KOFIA 자동 수집은 미구현 → 안내 메시지와 함께 예외 발생
        curve = risk_free.fetch_kofia_ytm(inputs["inputs"]["valuation_date"])

    rate = risk_free.spot_rate(curve["maturities"], curve["yields"], maturity_years)
    return {
        "value": rate,
        "basis": "국고채 수익률 곡선 부트스트래핑 spot rate, 잔존만기 보간, 연속복리 환산",
        "detail": {
            "curve_date": curve.get("date"),
            "curve_source": curve.get("source", est.get("data_source")),
            "curve_file": curve_file,
            "maturities": curve["maturities"],
            "yields": curve["yields"],
            "target_maturity_years": maturity_years,
        },
    }


def sensitivity_analysis(pricer, base_s0: float, base_sigma: float) -> list[dict]:
    """민감도 분석: 주요변수를 하나씩 흔들어 재평가한다.

    pricer(s0, sigma, rf_shift) 형태의 평가 함수를 받아 실행하므로
    단일 금리/기간구조 어느 할인 방식이든 동일하게 동작한다.
    기본 시나리오: 기초자산 가액 ±10%, 변동성 ±5%p, 무위험이자율 ±1%p(평행이동)
    """
    scenarios = [
        ("기초자산 가액 -10%", {"s0": base_s0 * 0.9}),
        ("기초자산 가액 +10%", {"s0": base_s0 * 1.1}),
        ("변동성 -5%p", {"sigma": base_sigma - 0.05}),
        ("변동성 +5%p", {"sigma": base_sigma + 0.05}),
        ("무위험이자율 -1%p", {"rf_shift": -0.01}),
        ("무위험이자율 +1%p", {"rf_shift": +0.01}),
    ]
    results = []
    for label, override in scenarios:
        kwargs = {"s0": base_s0, "sigma": base_sigma, "rf_shift": 0.0, **override}
        if kwargs["sigma"] <= 0:
            results.append({"scenario": label, "value": None, "note": "변동성이 0 이하라 계산 불가"})
            continue
        results.append({"scenario": label, "value": pricer(**kwargs), "note": None})
    return results


def run(contract: dict, inputs: dict) -> dict:
    """가치평가 전체 파이프라인을 실행하고 결과 dict를 반환한다."""
    terms = contract["option_terms"]
    core = inputs["inputs"]

    # ── 필수 입력 확인: 없으면 기본값으로 채우지 않고 즉시 중단 ──
    for key in ("valuation_date", "underlying_price_krw"):
        if not core.get(key):
            raise ValueError(f"주요변수 '{key}'가 입력되지 않았습니다.")
    if terms["option_type"] != "call":
        raise NotImplementedError("현재 콜옵션 평가만 지원합니다.")

    # ── 1) 입력 해석 ──
    maturity_years = years_between(core["valuation_date"], core["maturity_date"])
    vol = resolve_volatility(inputs)
    rf = resolve_risk_free(inputs, maturity_years)

    # 배당: pays_dividend가 True일 때만 배당수익률을 반영
    dividend = core.get("dividend", {})
    dividend_yield = float(dividend.get("dividend_yield", 0.0)) if dividend.get("pays_dividend") else 0.0

    # 트리 스텝 결정: step_unit="weekly"면 실무 방식대로 주 단위 그리드 사용
    numerics = inputs.get("numerics", {})
    step_unit = numerics.get("step_unit")
    if step_unit == "weekly":
        steps = max(1, round(maturity_years * 365 / 7))
    elif step_unit:
        raise ValueError("step_unit은 'weekly' 또는 미지정(null)이어야 합니다.")
    else:
        steps = int(numerics.get("binomial_steps", 1000))
    step_years = maturity_years / steps
    american = terms.get("exercise_style", "european") != "european"

    # 할인 방식: "spot"(단일 spot rate) 또는 "term_structure"(스텝별 선도이자율)
    discounting = inputs.get("risk_free_estimation", {}).get("discounting", "spot")
    if discounting not in ("spot", "term_structure"):
        raise ValueError("discounting은 'spot' 또는 'term_structure'여야 합니다.")

    s0 = float(core["underlying_price_krw"])
    sigma = vol["value"]
    payoff = payoffs.call(float(core["strike_price_krw"]))

    # MC 교차검증·보고서용 파라미터 (rf는 만기 대응 spot rate — 유럽형에서는
    # 결정론적 기간구조 하의 할인과 동치이므로 교차검증 기준으로 유효하다)
    params = BinomialParams(
        s0=s0, sigma=sigma, rf=rf["value"], maturity=maturity_years,
        steps=steps, dividend_yield=dividend_yield,
    )

    # ── 2) 본 평가: 할인 방식에 따라 평가 함수(pricer)를 구성 ──
    if discounting == "term_structure":
        detail = rf.get("detail")
        if not detail:
            raise ValueError(
                "기간구조 할인에는 수익률 곡선이 필요합니다: "
                "risk_free_rate='auto'로 두고 ytm_curve_file을 지정하세요."
            )
        curve_m = np.asarray(detail["maturities"], dtype=float)
        curve_y = np.asarray(detail["yields"], dtype=float)

        def pricer(s0, sigma, rf_shift=0.0):
            # 금리 시나리오는 수익률 곡선 전체를 평행이동하여 반영
            forwards = risk_free.step_forward_rates(
                curve_m, curve_y + rf_shift, step_years, steps
            )
            return price_with_curve(
                s0, sigma, step_years, forwards, payoff,
                american=american, dividend_yield=dividend_yield,
            )

        rf["basis"] += " + 스텝별 선도이자율 할인 (기간구조 반영)"
        rf["detail"]["step_forward_rates"] = [
            round(float(f), 10)
            for f in risk_free.step_forward_rates(curve_m, curve_y, step_years, steps)
        ]
    else:

        def pricer(s0, sigma, rf_shift=0.0):
            p = BinomialParams(
                s0=s0, sigma=sigma, rf=rf["value"] + rf_shift,
                maturity=maturity_years, steps=steps, dividend_yield=dividend_yield,
            )
            return price(p, payoff, american=american)

    unit_value = pricer(s0, sigma)  # 1주당 가치
    quantity = int(terms["quantity_shares"])

    # ── 3) 몬테카를로 교차검증 (유럽형 전용, 미국형은 LSMC 구현 전까지 생략) ──
    if american:
        check = {"skipped": True, "reason": "미국형 조기행사는 LSMC 구현 후 교차검증 예정"}
    else:
        mc = monte_carlo.price_european(
            params,
            payoff,
            paths=int(numerics.get("monte_carlo_paths", 100_000)),
            seed=int(numerics.get("monte_carlo_seed", 42)),
            confidence=float(numerics.get("confidence_level", 0.95)),
        )
        check = monte_carlo.cross_check(unit_value, mc)

    # ── 4~5) 민감도 분석 + 결과 조립 ──
    # 이 dict가 결과 JSON으로 저장되며, 보고서 생성의 유일한 수치 원천이 된다
    return {
        "meta": {
            "engine": "CRR binomial (vectorized backward induction)",
            "run_at": datetime.now().isoformat(timespec="seconds"),
            "contract_name": contract["contract"]["contract_name"],
            "note": contract.get("meta", {}).get("description"),
        },
        "valuation_inputs": {
            "valuation_date": core["valuation_date"],
            "maturity_date": core["maturity_date"],
            "maturity_years": maturity_years,
            "underlying_price_krw": params.s0,
            "strike_price_krw": float(core["strike_price_krw"]),
            "volatility": vol,
            "risk_free_rate": rf,
            "dividend_yield": dividend_yield,
            "exercise_style": terms.get("exercise_style"),
            "binomial_steps": steps,
            "step_years": step_years,
            "step_unit": step_unit,
            "discounting": discounting,
        },
        "results": {
            "unit_value_krw": unit_value,
            "quantity_shares": quantity,
            "total_value_krw": unit_value * quantity,
        },
        "cross_check": check,
        "sensitivity": sensitivity_analysis(pricer, s0, sigma),
    }


def main(argv=None) -> None:
    """명령행 인터페이스: 인자 파싱 → 실행 → 결과 저장 → 요약 출력."""
    parser = argparse.ArgumentParser(description="이항모형 가치평가 실행")
    parser.add_argument("--contract", required=True, help="계약정보 JSON 경로")
    parser.add_argument("--inputs", required=True, help="평가 주요변수 JSON 경로")
    parser.add_argument("--output-dir", default="results", help="결과 저장 디렉토리")
    args = parser.parse_args(argv)

    contract = load_json(args.contract)
    inputs = load_json(args.inputs)
    result = run(contract, inputs)

    # 결과 JSON 저장 (ensure_ascii=False: 한글을 그대로 저장)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"valuation_result_{result['valuation_inputs']['valuation_date']}.json"
    out_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 터미널 요약 출력
    r = result["results"]
    cc = result["cross_check"]
    print(f"평가기준일: {result['valuation_inputs']['valuation_date']}")
    print(f"1주당 가치: {r['unit_value_krw']:,.2f} KRW")
    print(f"총 평가액 ({r['quantity_shares']:,}주): {r['total_value_krw']:,.0f} KRW")
    if cc.get("skipped"):
        print(f"교차검증: 생략 ({cc['reason']})")
    else:
        status = "합격" if cc["passed"] else "불합격"
        print(
            f"교차검증: {status} (MC {cc['mc_value']:,.2f}, "
            f"{int(cc['confidence']*100)}% CI [{cc['ci'][0]:,.2f}, {cc['ci'][1]:,.2f}])"
        )
    print(f"결과 저장: {out_path}")


if __name__ == "__main__":
    main()
