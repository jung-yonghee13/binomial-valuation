"""보고서 생성 파이프라인 검증: HTML 내용, 필수 기재사항, PDF 변환."""
import json
from pathlib import Path

import pytest

from valuation.report import build_report_html, find_browser, generate_report

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

RESULT = {
    "meta": {"engine": "CRR binomial", "run_at": "2026-07-12T00:00:00"},
    "valuation_inputs": {
        "valuation_date": "2026-06-30",
        "maturity_date": "2029-03-19",
        "maturity_years": 2.7205,
        "underlying_price_krw": 11000.0,
        "strike_price_krw": 12500.0,
        "volatility": {"value": 0.3955, "basis": "피어그룹 역사적 변동성 산술평균", "detail": None},
        "risk_free_rate": {"value": 0.0271, "basis": "국고채 spot rate", "detail": None},
        "dividend_yield": 0.0,
        "exercise_style": "european",
        "binomial_steps": 1000,
    },
    "results": {
        "unit_value_krw": 2594.26,
        "quantity_shares": 150000,
        "total_value_krw": 389139623.37,
    },
    "cross_check": {
        "model_value": 2594.26,
        "mc_value": 2609.45,
        "mc_std_error": 17.91,
        "confidence": 0.95,
        "ci": [2574.34, 2644.55],
        "paths": 100000,
        "seed": 42,
        "passed": True,
    },
    "sensitivity": [
        {"scenario": "기초자산 가액 -10%", "value": 1973.49, "note": None},
        {"scenario": "기초자산 가액 +10%", "value": 3281.56, "note": None},
    ],
}


class TestBuildReportHtml:
    def test_contains_core_values(self):
        html = build_report_html(CONTRACT, RESULT)
        assert "2,594.26" in html            # 1주당 가치
        assert "389,139,623" in html         # 총 평가액
        assert "150,000" in html             # 수량
        assert "주식회사 대한테크" in html
        assert "2026-06-30" in html          # 평가기준일

    def test_contains_toc_chapters(self):
        html = build_report_html(CONTRACT, RESULT)
        for chapter in (
            "Executive Summary",
            "용역의 목적, 범위 및 한계",
            "파생상품 가치평가",
            "CRR모형 가치평가방법",
        ):
            assert chapter in html

    def test_contains_mandatory_disclosures(self):
        # 행동 강령 4절 필수 기재사항
        html = build_report_html(CONTRACT, RESULT)
        assert "기술된 목적만을 위하여 타당" in html      # 평가기준일·목적 한정
        assert "투자자문이 아니" in html                  # 목적 외 사용 제한
        assert "어떠한 형태의 인증도 표명하지" in html    # 정보 신뢰의 한계
        assert "예측과 달라질 수 있으" in html            # 미래 예측의 불확실성
        assert "서면동의" in html                         # 공개 제한

    def test_fictional_data_banner(self):
        html = build_report_html(CONTRACT, RESULT)
        assert "검증용 가상 데이터" in html

    def test_cross_check_pass_rendered(self):
        html = build_report_html(CONTRACT, RESULT)
        assert "합격" in html
        assert "100,000" in html  # 경로 수

    def test_skipped_cross_check_rendered(self):
        result = json.loads(json.dumps(RESULT))
        result["cross_check"] = {"skipped": True, "reason": "LSMC 구현 전"}
        html = build_report_html(CONTRACT, result)
        assert "LSMC 구현 전" in html


class TestGenerateReport:
    @pytest.fixture()
    def io_paths(self, tmp_path):
        contract_path = tmp_path / "contract.json"
        result_path = tmp_path / "result.json"
        contract_path.write_text(json.dumps(CONTRACT, ensure_ascii=False), encoding="utf-8")
        result_path.write_text(json.dumps(RESULT, ensure_ascii=False), encoding="utf-8")
        return contract_path, result_path, tmp_path / "reports"

    def test_html_only(self, io_paths):
        contract_path, result_path, out_dir = io_paths
        out = generate_report(contract_path, result_path, out_dir, html_only=True)
        assert out.suffix == ".html"
        assert "평가보고서_2026-06-30" in out.name
        assert "2,594.26" in out.read_text(encoding="utf-8")

    @pytest.mark.skipif(find_browser() is None, reason="Edge/Chrome 미설치")
    def test_pdf_generation(self, io_paths):
        contract_path, result_path, out_dir = io_paths
        out = generate_report(contract_path, result_path, out_dir)
        assert out.suffix == ".pdf"
        assert out.stat().st_size > 10_000
        assert out.read_bytes()[:5] == b"%PDF-"
        assert not out.with_suffix(".html").exists()  # 중간 산출물 정리 확인
