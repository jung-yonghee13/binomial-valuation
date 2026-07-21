# -*- coding: utf-8 -*-
"""평가 실패 원인 진단 — 앱 기본값과 동일 조건으로 전체 파이프라인을 돌리고
어디서 깨지는지 full traceback을 출력한다.

사용:  python .claude/skills/reproduce-and-verify/scripts/diag_valuation.py
        [--date YYYY-MM-DD] [--s0 가격]

프로젝트 루트에서 실행하는 것을 전제로 한다(valuation 패키지 import).
"""
import argparse
import os
import platform
import sys
import traceback
from datetime import date
from pathlib import Path

# 이 스크립트는 저장소 깊은 하위(.claude/skills/.../scripts/)에 있으므로,
# 어디서 실행하든 valuation 패키지를 import할 수 있도록 프로젝트 루트를 찾아 sys.path에 넣는다.
# (Python은 스크립트 디렉토리만 sys.path에 넣고 cwd는 자동 추가하지 않는다.)
_here = Path(__file__).resolve()
_root = next((p for p in _here.parents if (p / "valuation" / "__init__.py").exists()), None)
if _root and str(_root) not in sys.path:
    sys.path.insert(0, str(_root))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="평가기준일 (기본: 오늘)")
    ap.add_argument("--s0", type=float, default=10000.0, help="기초자산 가액")
    args = ap.parse_args()
    val_date = args.date or date.today().isoformat()

    print("=" * 64)
    print("PYTHON :", sys.version.split()[0], "|", platform.platform())
    print("CWD    :", os.getcwd(), "| 평가기준일:", val_date)

    # 1) 패키지 버전
    for mod in ("numpy", "pandas", "scipy", "FinanceDataReader", "streamlit"):
        try:
            m = __import__(mod)
            print(f"  {mod:18s}", getattr(m, "__version__", "?"))
        except Exception as e:  # noqa: BLE001
            print(f"  {mod:18s} IMPORT FAIL: {e}")

    # 2) 데이터 소스 개별 점검 (실패 계층 1차 분류)
    print("-" * 64)
    try:
        from valuation import seibro
        c = seibro.fetch_treasury_curve(val_date)
        print(f"[SEIBRO] OK  기준일={c['date']}  구간수={len(c['maturities'])}")
    except Exception:  # noqa: BLE001
        print("[SEIBRO] FAIL  ↓ (urllib 계열 → 배포 환경 차단 의심)")
        traceback.print_exc()

    try:
        from valuation import volatility
        s = volatility.fetch_close_prices("053800", "2025-07-01", val_date)
        print(f"[FDR 안랩] OK  관측치={len(s)}")
    except Exception:  # noqa: BLE001
        print("[FDR] FAIL  ↓ (requests 계열 → 시세 소스 문제)")
        traceback.print_exc()

    # 3) 전체 평가 (앱 기본 샘플과 동일 조건)
    print("-" * 64)
    contract = {
        "meta": {"description": "진단"},
        "contract": {"contract_name": "진단 콜옵션"},
        "underlying": {"issuer": "진단", "security_type": "보통주",
                       "listing_status": "비상장", "ticker": ""},
        "option_terms": {"option_type": "call", "exercise_style": "european",
                         "quantity_shares": 1756688, "strike_price_krw": 12500.0,
                         "exercise_scope": 0.35,
                         "holders": [{"name": "A", "ratio": 0.4},
                                     {"name": "B", "ratio": 0.3},
                                     {"name": "C", "ratio": 0.3}],
                         "strike_growth_rate": 0.08, "closing_date": "2029-03-19"},
    }
    inputs = {
        "inputs": {"valuation_date": val_date, "underlying_price_krw": args.s0,
                   "strike_price_krw": 12500.0, "maturity_date": "2029-03-19",
                   "risk_free_rate": "auto", "volatility": "auto",
                   "dividend": {"pays_dividend": False, "dividend_yield": 0.0}},
        "volatility_estimation": {"peer_group": [
            {"name": "안랩", "ticker": "053800"},
            {"name": "더존비즈온", "ticker": "012510"},
            {"name": "한글과컴퓨터", "ticker": "030520"},
            {"name": "웹케시", "ticker": "053580"},
            {"name": "알서포트", "ticker": "131370"}],
            "lookback_years": 1.0, "annualization_factor": 252},
        "risk_free_estimation": {"discounting": "term_structure"},
        "numerics": {"binomial_steps": 1000, "step_unit": "weekly",
                     "monte_carlo_paths": 100000, "monte_carlo_seed": 42,
                     "confidence_level": 0.95},
    }
    try:
        from valuation import run_valuation
        r = run_valuation.run(contract, inputs)
        rf = r["valuation_inputs"]["risk_free_rate"]
        print("[평가] 성공  1주당 =", round(r["results"]["unit_value_krw"], 2), "원")
        print("        교차검증 =", "합격" if r["cross_check"].get("passed") else r["cross_check"])
        print("        무위험이자율 basis =", rf.get("basis"))
        if rf.get("fallback_used"):
            print("        ⚠ 폴백 사용됨 (스냅샷) — 투명 표기 확인 필요")
    except Exception:  # noqa: BLE001
        print("[평가] 실패 ↓↓↓ 아래 traceback을 그대로 공유하세요")
        traceback.print_exc()
    print("=" * 64)


if __name__ == "__main__":
    main()
