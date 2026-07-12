"""평가 실행 진입점.

계약정보(JSON)와 평가 주요변수(JSON)를 입력받아
  1) 변동성·무위험이자율 해석(자동 산출 또는 직접 입력)
  2) CRR 이항모형 평가
  3) 몬테카를로 교차검증 (유럽형)
  4) 민감도 분석
을 수행하고 결과 JSON을 저장한다. 이 결과가 평가보고서 생성의 입력이 된다.

사용 예:
    python -m valuation.run_valuation --contract data/sample_contract.json \
        --inputs data/my_inputs.json --output-dir results
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path

from valuation import monte_carlo, payoffs, risk_free, volatility
from valuation.binomial import BinomialParams, price

DAYS_PER_YEAR = 365.0  # ACT/365


def load_json(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def years_between(start: str, end: str) -> float:
    d0 = date.fromisoformat(str(start))
    d1 = date.fromisoformat(str(end))
    days = (d1 - d0).days
    if days <= 0:
        raise ValueError(f"만기일({end})이 평가기준일({start}) 이후여야 합니다.")
    return days / DAYS_PER_YEAR


def resolve_volatility(inputs: dict) -> dict:
    """변동성을 해석한다: 숫자면 그대로, 'auto'면 피어그룹 자동 산출."""
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
    """무위험이자율을 해석한다: 숫자면 그대로(연속복리 가정), 'auto'면 spot rate 산출."""
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


def sensitivity_analysis(
    base: BinomialParams, payoff, american: bool, steps: int
) -> list[dict]:
    """주요변수 변동에 따른 평가액 변화 (기초자산 ±10%, 변동성 ±5%p, 금리 ±1%p)."""
    scenarios = [
        ("기초자산 가액 -10%", {"s0": base.s0 * 0.9}),
        ("기초자산 가액 +10%", {"s0": base.s0 * 1.1}),
        ("변동성 -5%p", {"sigma": base.sigma - 0.05}),
        ("변동성 +5%p", {"sigma": base.sigma + 0.05}),
        ("무위험이자율 -1%p", {"rf": base.rf - 0.01}),
        ("무위험이자율 +1%p", {"rf": base.rf + 0.01}),
    ]
    results = []
    for label, override in scenarios:
        kwargs = {
            "s0": base.s0,
            "sigma": base.sigma,
            "rf": base.rf,
            "maturity": base.maturity,
            "steps": steps,
            "dividend_yield": base.dividend_yield,
            **override,
        }
        if kwargs["sigma"] <= 0:
            results.append({"scenario": label, "value": None, "note": "변동성이 0 이하라 계산 불가"})
            continue
        value = price(BinomialParams(**kwargs), payoff, american=american)
        results.append({"scenario": label, "value": value, "note": None})
    return results


def run(contract: dict, inputs: dict) -> dict:
    """가치평가 전체 파이프라인을 실행하고 결과 dict를 반환한다."""
    terms = contract["option_terms"]
    core = inputs["inputs"]

    for key in ("valuation_date", "underlying_price_krw"):
        if not core.get(key):
            raise ValueError(f"주요변수 '{key}'가 입력되지 않았습니다.")
    if terms["option_type"] != "call":
        raise NotImplementedError("현재 콜옵션 평가만 지원합니다.")

    maturity_years = years_between(core["valuation_date"], core["maturity_date"])
    vol = resolve_volatility(inputs)
    rf = resolve_risk_free(inputs, maturity_years)

    dividend = core.get("dividend", {})
    dividend_yield = float(dividend.get("dividend_yield", 0.0)) if dividend.get("pays_dividend") else 0.0

    numerics = inputs.get("numerics", {})
    steps = int(numerics.get("binomial_steps", 1000))
    american = terms.get("exercise_style", "european") != "european"

    params = BinomialParams(
        s0=float(core["underlying_price_krw"]),
        sigma=vol["value"],
        rf=rf["value"],
        maturity=maturity_years,
        steps=steps,
        dividend_yield=dividend_yield,
    )
    payoff = payoffs.call(float(core["strike_price_krw"]))

    unit_value = price(params, payoff, american=american)
    quantity = int(terms["quantity_shares"])

    # 몬테카를로 교차검증 (유럽형 전용, 미국형은 LSMC 구현 전까지 생략)
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
        },
        "results": {
            "unit_value_krw": unit_value,
            "quantity_shares": quantity,
            "total_value_krw": unit_value * quantity,
        },
        "cross_check": check,
        "sensitivity": sensitivity_analysis(params, payoff, american, steps),
    }


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="이항모형 가치평가 실행")
    parser.add_argument("--contract", required=True, help="계약정보 JSON 경로")
    parser.add_argument("--inputs", required=True, help="평가 주요변수 JSON 경로")
    parser.add_argument("--output-dir", default="results", help="결과 저장 디렉토리")
    args = parser.parse_args(argv)

    contract = load_json(args.contract)
    inputs = load_json(args.inputs)
    result = run(contract, inputs)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"valuation_result_{result['valuation_inputs']['valuation_date']}.json"
    out_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

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
