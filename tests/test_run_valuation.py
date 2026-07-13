"""run_valuation 파이프라인 검증: 기간구조 모드 통합, 주 단위 스텝, 입력 검증."""
import copy

import pytest

from valuation.run_valuation import run

CONTRACT = {
    "meta": {"description": "검증용 가상 계약 데이터"},
    "contract": {
        "contract_name": "주식 콜옵션 부여 계약",
        "contract_date": "2026-03-20",
        "investor": "주식회사 한빛인베스트먼트",
        "grantor": "주식회사 대한테크",
        "governing_document": "주식 콜옵션 부여 계약서",
    },
    "underlying": {
        "issuer": "주식회사 대한테크",
        "security_type": "기명식 보통주",
        "listing_status": "비상장",
    },
    "option_terms": {
        "option_type": "call",
        "exercise_style": "european",
        "quantity_shares": 150000,
        "strike_price_krw": 12500,
        "settlement": "차액 현금결제",
    },
}

# 변동성은 네트워크 없이 테스트하기 위해 직접 입력, 금리는 샘플 곡선 파일 사용
BASE_INPUTS = {
    "inputs": {
        "valuation_date": "2026-06-30",
        "underlying_price_krw": 11000,
        "strike_price_krw": 12500,
        "maturity_date": "2029-03-19",
        "risk_free_rate": "auto",
        "volatility": 0.40,
        "dividend": {"pays_dividend": False, "dividend_yield": 0.0},
    },
    "risk_free_estimation": {
        "ytm_curve_file": "data/sample_ytm_curve.json",
        "discounting": "spot",
    },
    "numerics": {
        "binomial_steps": 500,
        "monte_carlo_paths": 100000,
        "monte_carlo_seed": 42,
        "confidence_level": 0.95,
    },
}


def make_inputs(**overrides):
    inputs = copy.deepcopy(BASE_INPUTS)
    inputs["risk_free_estimation"].update(overrides.pop("risk_free_estimation", {}))
    inputs["numerics"].update(overrides.pop("numerics", {}))
    inputs["inputs"].update(overrides)
    return inputs


class TestTermStructureMode:
    def test_runs_and_passes_cross_check(self):
        result = run(CONTRACT, make_inputs(
            risk_free_estimation={"discounting": "term_structure"}
        ))
        assert result["valuation_inputs"]["discounting"] == "term_structure"
        assert result["cross_check"]["passed"] is True
        assert result["results"]["unit_value_krw"] > 0
        # 스텝별 선도이자율이 결과에 기록되어야 한다 (보고서 근거)
        forwards = result["valuation_inputs"]["risk_free_rate"]["detail"]["step_forward_rates"]
        assert len(forwards) == result["valuation_inputs"]["binomial_steps"]

    def test_close_to_spot_mode_for_european(self):
        # 유럽형에서는 기간구조 할인과 만기 spot 단일 할인이 근사해야 한다
        spot = run(CONTRACT, make_inputs())
        term = run(CONTRACT, make_inputs(
            risk_free_estimation={"discounting": "term_structure"}
        ))
        v1 = spot["results"]["unit_value_krw"]
        v2 = term["results"]["unit_value_krw"]
        assert v2 == pytest.approx(v1, rel=0.01)

    def test_requires_curve_detail(self):
        # 금리를 숫자로 직접 입력하면 곡선이 없으므로 기간구조 할인 불가
        with pytest.raises(ValueError, match="곡선"):
            run(CONTRACT, make_inputs(
                risk_free_rate=0.03,
                risk_free_estimation={"discounting": "term_structure"},
            ))

    def test_invalid_discounting_raises(self):
        with pytest.raises(ValueError, match="discounting"):
            run(CONTRACT, make_inputs(risk_free_estimation={"discounting": "flat"}))

    def test_sensitivity_uses_term_structure(self):
        result = run(CONTRACT, make_inputs(
            risk_free_estimation={"discounting": "term_structure"}
        ))
        scenarios = {s["scenario"]: s["value"] for s in result["sensitivity"]}
        base = result["results"]["unit_value_krw"]
        # 금리 평행이동 시나리오가 계산되고 방향이 맞아야 한다 (콜: 금리↑ -> 가치↑)
        assert scenarios["무위험이자율 +1%p"] > base > scenarios["무위험이자율 -1%p"]


class TestWeeklySteps:
    def test_weekly_step_unit_sets_steps(self):
        result = run(CONTRACT, make_inputs(numerics={"step_unit": "weekly"}))
        maturity_years = result["valuation_inputs"]["maturity_years"]
        assert result["valuation_inputs"]["binomial_steps"] == round(maturity_years * 365 / 7)
        assert result["valuation_inputs"]["step_unit"] == "weekly"

    def test_unknown_step_unit_raises(self):
        with pytest.raises(ValueError, match="step_unit"):
            run(CONTRACT, make_inputs(numerics={"step_unit": "daily"}))
