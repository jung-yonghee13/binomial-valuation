# -*- coding: utf-8 -*-
"""이항모형 가치평가 대시보드 (Streamlit).

좌측에 계약조건·주요변수·피어그룹을 입력하면, 우측 미리보기 패널에
평가 결과(지표·산출 내역·민감도)와 평가보고서 미리보기가 표시되고
PDF 보고서까지 내려받을 수 있다.

실행:  streamlit run app.py
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from valuation import report as report_module
from valuation import run_valuation

ROOT = Path(__file__).parent
ACCENT = "#E8490F"  # 포인트 컬러 (보고서 오렌지 계열)

st.set_page_config(page_title="이항모형 가치평가", page_icon="📊", layout="wide")

# ── 스타일: 웜 크림 배경 + 흰색 라운드 카드 + 보고서 챕터 헤드 톤 ──
st.markdown(
    """
    <style>
    .stApp { background: #F7F1EA; }
    header[data-testid="stHeader"] { background: transparent; }
    .block-container { padding-top: 1.1rem; }

    .brand-title {
        color: #E8490F; font-size: 2.3rem; font-weight: 800;
        letter-spacing: -0.01em; line-height: 1.1; margin: 0 0 0.3rem 0;
        text-align: center;
    }
    .brand-sub { color: #6b6257; font-size: 0.92rem; margin-bottom: 0.6rem;
        text-align: center; }

    /* 섹션 카드 */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background: #FFFFFF; border: 1px solid #EFE3D6; border-radius: 18px;
        box-shadow: 0 3px 14px rgba(120, 80, 40, 0.07);
        padding: 0.4rem 0.9rem 0.7rem 0.9rem;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] h3 {
        color: #2d2d2d; font-size: 1.12rem; padding-top: 0.4rem; font-weight: 800;
        border-bottom: 2px solid #F4D9C8; padding-bottom: 0.45rem;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] h3 .num {
        color: #FB5607; font-size: 1.55rem; font-weight: 800; margin-right: 0.5rem;
        vertical-align: -0.08rem;
    }

    /* ── 입력 위젯: 테두리를 넣어 배경과 확실히 구분 ── */
    div[data-baseweb="input"], div[data-baseweb="select"] > div,
    div[data-baseweb="base-input"] {
        background: #FFFFFF !important;
        border: 1.5px solid #E3CDBB !important;
        border-radius: 10px !important;
        transition: border-color .15s ease, box-shadow .15s ease;
    }
    div[data-baseweb="input"]:hover, div[data-baseweb="select"] > div:hover {
        border-color: #D3A987 !important;
    }
    div[data-baseweb="input"]:focus-within, div[data-baseweb="select"] > div:focus-within {
        border-color: #E8490F !important;
        box-shadow: 0 0 0 3px rgba(232, 73, 15, 0.13) !important;
    }
    div[data-baseweb="input"] input, div[data-baseweb="base-input"] input {
        background: transparent !important;
    }
    div[data-testid="stNumberInputStepUp"], div[data-testid="stNumberInputStepDown"] {
        background: #FFF8F2; border-left: 1px solid #E3CDBB;
    }
    div[data-testid="stFileUploaderDropzone"] {
        background: #FFF8F2; border: 1.5px dashed #E3A77E; border-radius: 12px;
    }
    div[data-testid="stDataFrame"], div[data-testid="stDataEditor"] {
        border: 1.5px solid #E3CDBB; border-radius: 10px; overflow: hidden;
    }

    /* 버튼: 오렌지 필 */
    .stButton > button, .stDownloadButton > button {
        border-radius: 14px; font-weight: 700; padding: 0.55rem 1rem;
    }
    .stButton > button[kind="primary"] {
        background: #E8490F; border: none;
        box-shadow: 0 4px 12px rgba(232, 73, 15, 0.25);
    }
    .stButton > button[kind="primary"]:hover { background: #C93E0C; }

    /* 지표 타일 */
    div[data-testid="stMetric"] {
        background: #FFF8F2; border: 1px solid #F4D9C8; border-radius: 14px;
        padding: 0.6rem 0.9rem;
    }
    div[data-testid="stMetricValue"] { color: #E8490F; font-weight: 800; font-size: 1.5rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="brand-title">이항모형 가치평가 엔진</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="brand-sub">계약조건과 피어그룹만 입력하면 — 변동성·무위험이자율 자동 수집 → '
    "CRR 이항모형 평가 → 몬테카를로 교차검증 → PDF 평가보고서까지 자동 수행합니다.</div>",
    unsafe_allow_html=True,
)

left, right = st.columns([3, 2], gap="medium")

# ════════════════════════════ 좌측: 입력 폼 ════════════════════════════
with left:
    # ── 01 계약 조건 ──
    with st.container(border=True):
        st.markdown('### <span class="num">01</span> 계약 조건', unsafe_allow_html=True)

        up_col, _ = st.columns(2)  # 첨부 영역은 절반 폭만 차지
        with up_col:
            uploaded = st.file_uploader(
                "계약정보 JSON 첨부 (선택)",
                type=["json"],
                help="계약서 PDF의 자동 분석·추출은 Claude 에이전트 세션에서 수행합니다. "
                     "추출된 계약정보 JSON을 첨부하면 아래 입력값의 기본값으로 사용됩니다.",
            )
        prefill = {}
        if uploaded is not None:
            try:
                prefill = json.loads(uploaded.read().decode("utf-8-sig"))
                st.success(f"계약정보 로드: {prefill.get('contract', {}).get('contract_name', '(이름 없음)')}")
            except Exception as exc:
                st.error(f"JSON 파싱 실패: {exc}")

        pc = prefill.get("contract", {})
        pu = prefill.get("underlying", {})
        pt = prefill.get("option_terms", {})

        c1, c2 = st.columns(2)
        with c1:
            contract_name = st.text_input("계약명", pc.get("contract_name", "주식 콜옵션 부여 계약"))
            investor = st.text_input("투자자 (옵션 보유자)", pc.get("investor", ""))
            grantor = st.text_input("부여자 (거래상대방)", pc.get("grantor", ""))
            issuer = st.text_input("기초자산 발행회사", pu.get("issuer", ""))
            security_type = st.text_input("주식 종류", pu.get("security_type", "기명식 보통주"))
        with c2:
            contract_date = st.date_input("계약일", date.fromisoformat(pc.get("contract_date", "2026-03-20")))
            maturity_date = st.date_input("거래종결일 (만기)", date.fromisoformat(pt.get("closing_date", "2029-03-19")))
            listing_status = st.selectbox("상장 여부", ["비상장", "상장"],
                                          index=0 if pu.get("listing_status", "비상장") == "비상장" else 1)
            exercise_style = st.selectbox(
                "행사방식", ["european", "american"],
                format_func=lambda s: "유럽형 (만기 일괄 행사)" if s == "european" else "미국형 (기간 중 행사 가능)",
                index=0 if pt.get("exercise_style", "european") == "european" else 1)
            settlement = st.text_input("결제방식", pt.get("settlement", "차액 현금결제 또는 실물인수"))

        c3, c4 = st.columns(2)
        with c3:
            quantity = st.number_input("대상주식수량 (주)", min_value=1,
                                       value=int(pt.get("quantity_shares", 150000)), step=1000,
                                       help="계약상 기초자산 총 주식수 (행사범위·행사비율 적용 전)")
        with c4:
            strike = st.number_input("행사가격 (원/주)", min_value=1.0,
                                     value=float(pt.get("strike_price_krw", 12500)), step=100.0,
                                     help="계약금액 기준 행사가격. 옵션 대가율이 있으면 이 값이 기준가가 됩니다.")

    # ── 02 콜옵션 조건 ──
    with st.container(border=True):
        st.markdown('### <span class="num">02</span> 콜옵션 조건', unsafe_allow_html=True)
        st.caption("계약서상 행사범위·행사비율·옵션 대가(보장수익률) 조건. "
                   "콜옵션 수량 = 대상주식수량 × 행사범위 × 행사비율")

        t1, t2, t3 = st.columns(3)
        with t1:
            exercise_scope = st.number_input(
                "행사범위 (%)", 0.01, 100.0,
                float(pt.get("exercise_scope", 1.0)) * 100, 1.0,
                help="대상주식 중 콜옵션 행사 대상이 되는 비율 (예: 35%)")
        with t2:
            allocation_ratio = st.number_input(
                "행사비율 (%)", 0.01, 100.0,
                float(pt.get("allocation_ratio", 1.0)) * 100, 1.0,
                help="행사 대상 중 평가대상 보유자에게 귀속되는 비율 (예: 40%)")
        with t3:
            strike_growth = st.number_input(
                "옵션 대가율 (연 %, 0=고정)", 0.0, 50.0,
                float(pt.get("strike_growth_rate", 0.0)) * 100, 0.5,
                help="행사 시점까지 보장하는 연 수익률. 행사가격이 K(t) = 기준가 × (1+대가율)^t 로 "
                     "복리 상승합니다. 0이면 만기까지 고정 행사가격.")

        _opt_qty = round(quantity * exercise_scope / 100 * allocation_ratio / 100)
        _years = max((maturity_date - contract_date).days, 0) / 365
        _strike_end = strike * (1 + strike_growth / 100) ** _years
        st.markdown(
            f"→ **콜옵션 수량 {_opt_qty:,}주** "
            f"({quantity:,}주 × {exercise_scope:g}% × {allocation_ratio:g}%) · "
            f"**행사가격 {strike:,.0f}원**"
            + (f" → 만기 시 {_strike_end:,.0f}원" if strike_growth > 0 else " (만기까지 고정)")
        )

    # ── 03 평가 주요변수 ──
    with st.container(border=True):
        st.markdown('### <span class="num">03</span> 평가 주요변수', unsafe_allow_html=True)
        c5, c6 = st.columns(2)
        with c5:
            valuation_date = st.date_input("평가기준일", date(2026, 6, 30))
            s0 = st.number_input("기초자산 가액 (원/주)", min_value=1.0, value=11000.0, step=100.0,
                                 help="비상장이면 평가자가 합리적으로 추정한 주당 가액")
        with c6:
            s0_basis = st.text_input("기초자산 가액 추정 근거", "최근 거래가액 참조")
            pays_dividend = st.checkbox("배당 있음", value=False)
            dividend_yield = st.number_input("배당수익률 (%)", 0.0, 20.0, 0.0, 0.1, disabled=not pays_dividend)

    # ── 03 피어그룹 ──
    with st.container(border=True):
        st.markdown('### <span class="num">04</span> 피어그룹 — 변동성 자동 산출', unsafe_allow_html=True)
        st.caption("유사 상장기업과 6자리 종목코드를 지정하면 일별 종가를 자동 수집해 연환산 변동성 평균을 계산합니다.")

        default_peers = pd.DataFrame(
            prefill.get("volatility_estimation", {}).get("peer_group")
            or [
                {"name": "안랩", "ticker": "053800"},
                {"name": "더존비즈온", "ticker": "012510"},
                {"name": "한글과컴퓨터", "ticker": "030520"},
                {"name": "웹케시", "ticker": "053580"},
                {"name": "알서포트", "ticker": "131370"},
            ]
        )
        cp1, cp2 = st.columns([2, 1])
        with cp1:
            peers_df = st.data_editor(default_peers, num_rows="dynamic", use_container_width=True,
                                      column_config={"name": "기업명", "ticker": "종목코드"})
        with cp2:
            lookback = st.number_input("수집 기간 (년)", 0.5, 5.0, 1.0, 0.5)
            manual_vol = st.number_input("변동성 직접 입력 (%, 0=자동)", 0.0, 200.0, 0.0, 1.0,
                                         help="0보다 크게 입력하면 피어그룹 자동 산출 대신 이 값을 사용")

    # ── 04 무위험이자율·계산 설정 ──
    with st.container(border=True):
        st.markdown('### <span class="num">05</span> 무위험이자율 · 계산 설정', unsafe_allow_html=True)
        c7, c8 = st.columns(2)
        with c7:
            rf_mode = st.selectbox("무위험이자율", ["auto", "manual"],
                                   format_func=lambda s: "자동 — Seibro 국고채 수익률 수집" if s == "auto" else "직접 입력")
            manual_rf = st.number_input("직접 입력 시 금리 (%, 연속복리)", 0.0, 20.0, 3.0, 0.05,
                                        disabled=(rf_mode == "auto"))
            discounting = st.selectbox(
                "할인 방식", ["term_structure", "spot"],
                format_func=lambda s: "기간구조 — 스텝별 선도이자율 (실무 방식)" if s == "term_structure" else "단일 spot rate")
        with c8:
            step_unit = st.selectbox("트리 스텝", ["weekly", "custom"],
                                     format_func=lambda s: "주 단위 (실무 방식)" if s == "weekly" else "스텝 수 직접 지정")
            custom_steps = st.number_input("스텝 수", 50, 5000, 1000, 50, disabled=(step_unit == "weekly"))
            mc_paths = st.number_input("몬테카를로 경로 수", 10_000, 1_000_000, 100_000, 10_000)

    run_clicked = st.button("가치평가 실행", type="primary", use_container_width=True)

# ── 실행 ──
if run_clicked:
    contract = {
        "meta": {"description": "대시보드 입력 계약정보"},
        "contract": {
            "contract_name": contract_name,
            "contract_date": contract_date.isoformat(),
            "investor": investor or "(미입력)",
            "grantor": grantor or "(미입력)",
            "governing_document": f"{contract_name} ({contract_date.isoformat()} 체결)",
        },
        "underlying": {
            "issuer": issuer or "(미입력)",
            "security_type": security_type,
            "listing_status": listing_status,
        },
        "option_terms": {
            "option_type": "call",
            "exercise_style": exercise_style,
            "quantity_shares": int(quantity),
            "strike_price_krw": float(strike),
            "exercise_scope": exercise_scope / 100.0,
            "allocation_ratio": allocation_ratio / 100.0,
            "strike_growth_rate": strike_growth / 100.0,
            "closing_date": maturity_date.isoformat(),
            "settlement": settlement,
        },
    }
    peer_group = [
        {"name": str(r["name"]).strip(), "ticker": str(r["ticker"]).strip().zfill(6)}
        for _, r in peers_df.iterrows()
        if str(r.get("ticker", "")).strip()
    ]
    inputs = {
        "inputs": {
            "valuation_date": valuation_date.isoformat(),
            "underlying_price_krw": float(s0),
            "strike_price_krw": float(strike),
            "maturity_date": maturity_date.isoformat(),
            "risk_free_rate": "auto" if rf_mode == "auto" else manual_rf / 100.0,
            "volatility": "auto" if manual_vol == 0.0 else manual_vol / 100.0,
            "dividend": {"pays_dividend": pays_dividend, "dividend_yield": dividend_yield / 100.0},
        },
        "volatility_estimation": {"peer_group": peer_group, "lookback_years": float(lookback),
                                  "annualization_factor": 252},
        "risk_free_estimation": {"discounting": discounting},
        "numerics": {
            "binomial_steps": int(custom_steps),
            "step_unit": "weekly" if step_unit == "weekly" else None,
            "monte_carlo_paths": int(mc_paths),
            "monte_carlo_seed": 42,
            "confidence_level": 0.95,
        },
    }
    try:
        with right, st.spinner("피어 주가·국고채 수익률 수집 및 평가 계산 중..."):
            result = run_valuation.run(contract, inputs)
        st.session_state["result"] = result
        st.session_state["contract"] = contract
        st.session_state.pop("pdf", None)
    except Exception as exc:
        with right:
            st.error(f"평가 실패: {exc}")

# ════════════════════════════ 우측: 결과 미리보기 ════════════════════════════
with right:
    with st.container(border=True):
        st.markdown('### <span class="num">06</span> 결과 미리보기', unsafe_allow_html=True)

        if "result" not in st.session_state:
            st.info("좌측에 조건을 입력하고 **가치평가 실행**을 누르면 결과와 보고서 미리보기가 여기에 표시됩니다.")
        else:
            result = st.session_state["result"]
            contract = st.session_state["contract"]
            vi = result["valuation_inputs"]
            r = result["results"]
            cc = result["cross_check"]

            m1, m2 = st.columns(2)
            m1.metric("1주당 공정가치", f"{r['unit_value_krw']:,.0f} 원")
            m2.metric("총 평가액", f"{r['total_value_krw'] / 1e8:,.2f} 억원",
                      help=f"{r['unit_value_krw']:,.2f}원 × {r['quantity_shares']:,}주")
            m3, m4 = st.columns(2)
            if cc.get("skipped"):
                m3.metric("몬테카를로 교차검증", "생략", help=cc["reason"])
            else:
                m3.metric("몬테카를로 교차검증", "합격 ✓" if cc["passed"] else "불합격 ✗",
                          help=f"MC {cc['mc_value']:,.2f}원, 95% CI [{cc['ci'][0]:,.2f}, {cc['ci'][1]:,.2f}]")
            m4.metric("변동성 / 금리",
                      f"{vi['volatility']['value']*100:.2f}% / {vi['risk_free_rate']['value']*100:.3f}%")

            tab0, tab1, tab2, tab3, tab4 = st.tabs(
                ["보고서 미리보기", "변동성", "금리·선도", "민감도", "JSON"])

            with tab0:
                report_html = report_module.build_report_html(contract, result)
                components.html(report_html, height=620, scrolling=True)

            with tab1:
                detail = vi["volatility"].get("detail")
                if detail:
                    st.caption(f"수집 {detail['period']['start']} ~ {detail['period']['end']} · "
                               f"{detail['data_source']} · 연환산 √{detail['trading_days']}")
                    peers_out = pd.DataFrame(detail["peers"])
                    peers_out["volatility"] = (peers_out["volatility"] * 100).round(2)
                    st.dataframe(
                        peers_out.rename(columns={"name": "기업명", "ticker": "종목코드",
                                                  "volatility": "변동성(%)", "observations": "관측치",
                                                  "first_date": "시작일", "last_date": "종료일"}),
                        use_container_width=True, hide_index=True)
                    st.markdown(f"**적용 변동성 (산술평균): {vi['volatility']['value']*100:.2f}%**")
                else:
                    st.info(f"직접 입력값 사용: {vi['volatility']['value']*100:.2f}%")

            with tab2:
                detail = vi["risk_free_rate"].get("detail")
                if detail:
                    st.caption(f"곡선 기준일 {detail.get('curve_date')} · "
                               f"{detail.get('curve_source') or 'Seibro'}")
                    st.markdown("**국고채 만기수익률 곡선**")
                    curve_df = pd.DataFrame({"만기(년)": detail["maturities"],
                                             "수익률(%)": [y * 100 for y in detail["yields"]]})
                    st.line_chart(curve_df.set_index("만기(년)"), color=ACCENT, height=220)
                    forwards = detail.get("step_forward_rates")
                    if forwards:
                        st.markdown("**스텝별 선도이자율 (연환산 %)**")
                        step_years = vi["step_years"]
                        fwd_df = pd.DataFrame({
                            "경과(년)": [i * step_years for i in range(1, len(forwards) + 1)],
                            "선도이자율(%)": [((1 + f) ** (1 / step_years) - 1) * 100 for f in forwards],
                        })
                        st.line_chart(fwd_df.set_index("경과(년)"), color=ACCENT, height=220)
                    st.markdown(f"**적용 무위험이자율: {vi['risk_free_rate']['value']*100:.4f}%** (연속복리)")
                else:
                    st.info(f"직접 입력값 사용: {vi['risk_free_rate']['value']*100:.3f}% (연속복리)")

            with tab3:
                base = r["unit_value_krw"]
                rows = [{"시나리오": "기준 (Base)", "1주당 가치(원)": round(base, 2), "기준 대비(%)": 0.0}]
                for s in result["sensitivity"]:
                    if s["value"] is not None:
                        rows.append({"시나리오": s["scenario"], "1주당 가치(원)": round(s["value"], 2),
                                     "기준 대비(%)": round((s["value"] / base - 1) * 100, 2)})
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            with tab4:
                st.caption("평가 투입변수·산출 내역 전체 (보고서의 수치 원천)")
                st.json(result, expanded=False)

            # ── 산출물 다운로드 ──
            out_dir = ROOT / "results"
            out_dir.mkdir(exist_ok=True)
            contract_path = out_dir / "dashboard_contract.json"
            result_path = out_dir / f"valuation_result_{vi['valuation_date']}.json"
            contract_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")
            result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

            d1, d2 = st.columns(2)
            with d1:
                st.download_button("결과 JSON (계산 과정)",
                                   json.dumps(result, ensure_ascii=False, indent=2),
                                   file_name=result_path.name, mime="application/json",
                                   use_container_width=True)
            with d2:
                if st.button("PDF 평가보고서 생성", use_container_width=True):
                    try:
                        with st.spinner("PDF 변환 중..."):
                            pdf_path = report_module.generate_report(contract_path, result_path, out_dir)
                        st.session_state["pdf"] = (pdf_path.name, pdf_path.read_bytes())
                    except Exception as exc:
                        st.error(f"보고서 생성 실패: {exc}")
                if "pdf" in st.session_state:
                    name, data = st.session_state["pdf"]
                    st.download_button("PDF 다운로드", data, file_name=name, mime="application/pdf",
                                       type="primary", use_container_width=True)
