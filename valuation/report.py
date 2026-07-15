"""평가보고서 PDF 생성 파이프라인.

run_valuation.py가 산출한 결과 JSON과 계약정보 JSON을 입력받아
보고서 목차 구조의 HTML을 생성하고, Edge/Chrome headless 인쇄로 PDF 변환한다.

원칙 (docs/conduct-guidelines.md):
- 수치는 전부 결과 JSON(파이썬 계산값)에서 가져오고, 계산되지 않은 숫자를 쓰지 않는다.
- 행동 강령 4절의 필수 기재사항(평가기준일·목적, 목적 외 사용 제한, 정보 신뢰의 한계,
  미래 예측의 불확실성, 주요 가정과 추정 근거, 공개 제한)을 포함한다.
- 가상 데이터 기반 보고서에는 검증용 가상 데이터임을 표기한다.

사용 예:
    python -m valuation.report --contract data/sample_contract.json \
        --result results/valuation_result_2026-06-30.json --output-dir reports
"""
from __future__ import annotations

import argparse
import html
import json
import os
import shutil
import subprocess
from datetime import date
from pathlib import Path

import numpy as np

from valuation import payoffs
from valuation.binomial import BinomialParams, build_trees

EXAMPLE_TREE_STEPS = 5

# PDF 변환에 쓸 브라우저 후보 (윈도우 로컬 / 리눅스 배포 환경 모두 대응)
BROWSER_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]
# 리눅스(Streamlit Cloud 등)에서는 PATH에서 찾는다 (packages.txt로 chromium 설치)
BROWSER_COMMANDS = ["chromium", "chromium-browser", "google-chrome", "msedge"]

# 삼일PwC 리서치 문서 톤의 스타일: 오렌지 포인트 컬러, 명조체 대제목,
# 그라데이션 표지, 큰 오렌지 챕터 번호(01·02·03), 산세리프 본문과 넉넉한 여백
CSS = """
@page { size: A4; margin: 20mm 18mm; }
* { box-sizing: border-box;
    -webkit-print-color-adjust: exact; print-color-adjust: exact; }
:root {
  --orange: #D04A02;        /* PwC 오렌지 */
  --orange-bright: #FB5607;
  --orange-pale: #FBE9DE;
  --ink: #2d2d2d;
  --gray: #6b6b6b;
  --line: #d9d9d9;
}
body {
  font-family: 'Malgun Gothic', '맑은 고딕', 'NanumGothic', 'Noto Sans CJK KR', 'Noto Sans KR', sans-serif;
  font-size: 10pt; line-height: 1.7; color: var(--ink); margin: 0;
}
.serif { font-family: 'Batang', '바탕', 'NanumMyeongjo', 'Noto Serif CJK KR', Georgia, serif; }

/* ── 표지: 화이트 → 피치 그라데이션, 명조 대제목 ── */
.cover {
  height: 254mm; padding: 14mm 12mm; page-break-after: always;
  background: linear-gradient(135deg, #ffffff 30%, #fde3d3 65%, #f8ab77 100%);
  display: flex; flex-direction: column;
}
.cover .brand { font-size: 13pt; font-weight: 700; letter-spacing: 0.02em; }
.cover .brand .bar { display: inline-block; width: 9mm; height: 2.2mm;
  background: var(--orange-bright); margin-right: 3mm; vertical-align: middle; }
.cover .mid { margin-top: 70mm; }
.cover .label { font-size: 11.5pt; font-weight: 700; margin-bottom: 5mm; }
.cover .title { font-size: 27pt; line-height: 1.35; font-weight: 800;
  font-family: 'Malgun Gothic', '맑은 고딕', 'NanumGothic', 'Noto Sans CJK KR', 'Noto Sans KR', sans-serif; letter-spacing: -0.01em; }
.cover .subject { font-size: 11pt; margin-top: 8mm; color: #3a3a3a; }
.cover .bottom { margin-top: auto; }
.cover .date { font-size: 11pt; font-weight: 600; margin-bottom: 6mm; }
.cover .fictional {
  display: inline-block; padding: 2.2mm 6mm; margin-bottom: 5mm;
  border: 1.6px solid var(--orange); color: var(--orange);
  font-weight: 700; font-size: 10pt; background: rgba(255,255,255,0.6);
}
.cover .disclaimer { font-size: 8pt; color: #5a5a5a; line-height: 1.6;
  border-top: 1px solid rgba(0,0,0,0.25); padding-top: 3mm; }

/* ── 목차 ── */
.toc { page-break-after: always; padding-top: 10mm; }
.toc .toc-title { font-size: 20pt; font-weight: 800; margin-bottom: 12mm;
  font-family: 'Malgun Gothic', '맑은 고딕', 'NanumGothic', 'Noto Sans CJK KR', 'Noto Sans KR', sans-serif; }
.toc ol { line-height: 2.2; font-size: 10.5pt; }
.toc > ol > li { font-weight: 800; margin-bottom: 3mm; font-size: 11pt; }
.toc ol ol { font-weight: 400; font-size: 10pt; color: #444; }

/* ── 챕터 헤드: 큰 오렌지 번호 + 명조 제목 ── */
.chapter { page-break-before: always; }
.chapter-head { display: flex; align-items: flex-start; gap: 7mm;
  margin: 4mm 0 9mm; page-break-after: avoid; }
.chapter-num { font-size: 38pt; font-weight: 700; line-height: 1;
  color: var(--orange-bright); letter-spacing: -0.02em; }
.chapter-title { font-size: 17pt; font-weight: 800; line-height: 1.35;
  font-family: 'Malgun Gothic', '맑은 고딕', 'NanumGothic', 'Noto Sans CJK KR', 'Noto Sans KR', sans-serif; padding-top: 2mm;
  letter-spacing: -0.01em; }
.chapter-sub { font-size: 10.5pt; font-weight: 700; color: var(--ink); }

h3 { font-size: 11.5pt; margin: 8mm 0 3mm; page-break-after: avoid;
  font-weight: 800; border-left: 3.5px solid var(--orange-bright); padding-left: 3mm; }
h4 { font-size: 10.5pt; margin: 6mm 0 2.5mm; color: var(--orange);
  font-weight: 800; page-break-after: avoid; }

/* ── 표: 얇은 회색 괘선 + 오렌지 헤더 라인 ── */
table { border-collapse: collapse; width: 100%; margin: 3mm 0 6mm;
  page-break-inside: avoid; }
th, td { border: none; border-bottom: 1px solid var(--line);
  padding: 1.8mm 2.8mm; font-size: 9.5pt; }
tr:first-child th { border-top: 2px solid var(--orange); }
th { background: var(--orange-pale); font-weight: 600; text-align: left; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
.tree td, .tree th { text-align: right; font-size: 8.5pt; padding: 1.2mm 1.8mm; }

.passfail-pass { color: #1a7a2e; font-weight: 700; }
.passfail-fail { color: #b03030; font-weight: 700; }
.note { font-size: 8.5pt; color: var(--gray); }
.formula { background: #faf7f4; border-left: 3.5px solid var(--orange-bright);
  padding: 3mm 5mm; font-family: Consolas, monospace; font-size: 9.5pt; margin: 3mm 0; }
ul, ol { padding-left: 5.5mm; }
ul.limits li { margin-bottom: 2.5mm; }
ul li::marker { color: var(--orange-bright); }
"""


def esc(value) -> str:
    return html.escape(str(value))


def krw(x: float, decimals: int = 0) -> str:
    return f"{x:,.{decimals}f}"


def pct(x: float, decimals: int = 2) -> str:
    return f"{x * 100:.{decimals}f}%"


def _tree_table(matrix: np.ndarray, caption: str) -> str:
    """이항트리 배열(행 j=상승횟수, 열 t=경과스텝)을 HTML 표로 변환한다."""
    n = matrix.shape[0] - 1
    head = "".join(f"<th class='num'>t={t}</th>" for t in range(n + 1))
    rows = []
    for j in range(n, -1, -1):  # 상승 횟수가 많은 노드를 위에 표시
        cells = "".join(
            f"<td>{krw(matrix[j, t])}</td>" if not np.isnan(matrix[j, t]) else "<td></td>"
            for t in range(n + 1)
        )
        rows.append(f"<tr><th>u×{j}</th>{cells}</tr>")
    return (
        f"<p class='note'>{esc(caption)}</p>"
        f"<table class='tree'><tr><th></th>{head}</tr>{''.join(rows)}</table>"
    )


def _volatility_rows(vol: dict) -> str:
    detail = vol.get("detail")
    if not detail:
        return ""
    rows = "".join(
        f"<tr><td>{esc(p['name'])} ({esc(p['ticker'])})</td>"
        f"<td class='num'>{pct(p['volatility'])}</td>"
        f"<td class='num'>{p['observations']}</td>"
        f"<td>{esc(p['first_date'])} ~ {esc(p['last_date'])}</td></tr>"
        for p in detail["peers"]
    )
    return f"""
    <h3>피어그룹 변동성 산출 내역</h3>
    <table>
      <tr><th>대용기업</th><th class='num'>연환산 변동성</th><th class='num'>관측치</th><th>수집 기간</th></tr>
      {rows}
      <tr><th>산술평균 (적용 변동성)</th><th class='num'>{pct(detail['mean_volatility'])}</th>
          <th colspan='2'>출처: {esc(detail.get('data_source', '-'))}</th></tr>
    </table>"""


def _risk_free_rows(rf: dict) -> str:
    detail = rf.get("detail")
    if not detail:
        return ""
    pairs = "".join(
        f"<tr><td class='num'>{m}</td><td class='num'>{pct(y)}</td></tr>"
        for m, y in zip(detail["maturities"], detail["yields"])
    )
    return f"""
    <h3>무위험이자율 산출 내역</h3>
    <p>기준 수익률 곡선 (기준일: {esc(detail.get('curve_date', '-'))},
       출처: {esc(detail.get('curve_source') or 'Seibro 채권만기수익률')}) 에서
       부트스트래핑으로 spot rate 곡선을 산출하고, 잔존만기
       {detail['target_maturity_years']:.4f}년에 보간한 뒤 연속복리로 환산하였다.
       적용 무위험이자율: <b>{pct(rf['value'], 4)}</b> (연속복리)</p>
    <table style='width: 45%'>
      <tr><th class='num'>만기(년)</th><th class='num'>국고채 수익률</th></tr>
      {pairs}
    </table>"""


def _cross_check_section(check: dict) -> str:
    if check.get("skipped"):
        return f"<p>몬테카를로 교차검증은 수행하지 않았다. 사유: {esc(check['reason'])}</p>"
    status = (
        "<span class='passfail-pass'>합격</span>"
        if check["passed"]
        else "<span class='passfail-fail'>불합격</span>"
    )
    return f"""
    <p>이항모형 평가액의 신뢰성 확보를 위하여, 동일한 위험중립 가정과 파라미터 하에서
    계산 구조가 전혀 다른 몬테카를로 경로 시뮬레이션으로 독립 계산하여 비교하였다.
    본 교차검증은 <b>계산의 정확성에 대한 검증</b>이며, 평가 가정 자체의 타당성 검증과는
    구분된다. 판정 기준은 이항모형 평가액이 몬테카를로 추정치의
    {int(check['confidence'] * 100)}% 신뢰구간 내에 위치하는지 여부이다.</p>
    <table style='width: 70%'>
      <tr><th>이항모형 평가액 (1주당)</th><td class='num'>{krw(check['model_value'], 2)} 원</td></tr>
      <tr><th>몬테카를로 추정치 (1주당)</th><td class='num'>{krw(check['mc_value'], 2)} 원</td></tr>
      <tr><th>표준오차</th><td class='num'>{krw(check['mc_std_error'], 4)}</td></tr>
      <tr><th>{int(check['confidence'] * 100)}% 신뢰구간</th>
          <td class='num'>[{krw(check['ci'][0], 2)}, {krw(check['ci'][1], 2)}]</td></tr>
      <tr><th>경로 수 / 난수 시드</th><td class='num'>{check['paths']:,} / {check['seed']} (대조변량 적용)</td></tr>
      <tr><th>판정</th><td>{status}</td></tr>
    </table>"""


def _sensitivity_table(sensitivity: list[dict], base_value: float) -> str:
    rows = []
    for s in sensitivity:
        if s["value"] is None:
            rows.append(f"<tr><td>{esc(s['scenario'])}</td><td class='num'>-</td>"
                        f"<td class='num'>-</td><td>{esc(s.get('note') or '')}</td></tr>")
            continue
        change = (s["value"] / base_value - 1.0) * 100
        rows.append(
            f"<tr><td>{esc(s['scenario'])}</td><td class='num'>{krw(s['value'], 2)}</td>"
            f"<td class='num'>{change:+.2f}%</td><td></td></tr>"
        )
    return f"""
    <table style='width: 80%'>
      <tr><th>시나리오</th><th class='num'>1주당 가치 (원)</th><th class='num'>기준 대비</th><th>비고</th></tr>
      <tr><td>기준 (Base)</td><td class='num'>{krw(base_value, 2)}</td><td class='num'>-</td><td></td></tr>
      {''.join(rows)}
    </table>"""


def _holders_table(r: dict) -> str:
    """보유자별 콜옵션 수량·평가액 표를 생성한다 (보유자가 2명 이상일 때)."""
    holders = r.get("holders") or []
    if len(holders) < 2:
        return ""
    rows = "".join(
        f"<tr><td>{esc(h['name'])}</td><td class='num'>{pct(h['ratio'])}</td>"
        f"<td class='num'>{h['quantity_shares']:,} 주</td>"
        f"<td class='num'>{krw(h['value_krw'])} 원</td></tr>"
        for h in holders
    )
    return f"""
    <h4>보유자별 평가결과</h4>
    <p class="note">콜옵션 행사 대상 주식수 {r.get('scoped_shares', 0):,}주
    (대상주식 {r.get('total_shares', 0):,}주 × 행사범위 {pct(r.get('exercise_scope', 1.0))})를
    각 보유자의 행사비율로 배분하였다.</p>
    <table style='width: 92%'>
      <tr><th>보유자</th><th class='num'>행사비율</th><th class='num'>콜옵션 수량</th><th class='num'>평가액</th></tr>
      {rows}
      <tr><th>합계</th><th class='num'>{pct(r.get('allocation_ratio', 1.0))}</th>
          <th class='num'>{r['quantity_shares']:,} 주</th>
          <th class='num'>{krw(r['total_value_krw'])} 원</th></tr>
    </table>"""


def build_report_html(contract: dict, result: dict) -> str:
    """계약정보와 평가결과로부터 보고서 HTML 전문을 생성한다."""
    c = contract["contract"]
    u = contract["underlying"]
    terms = contract["option_terms"]
    vi = result["valuation_inputs"]
    r = result["results"]
    vol = vi["volatility"]
    rf = vi["risk_free_rate"]

    is_fictional = "가상" in str(contract.get("meta", {}).get("description", ""))
    fictional_banner = (
        "<div class='fictional'>검증용 가상 데이터 기반 보고서 — 실제 거래·실존 회사와 무관</div>"
        if is_fictional
        else ""
    )
    style_label = "유럽형 (만기 시점 일괄 행사)" if vi["exercise_style"] == "european" else "미국형 (기간 중 조기행사 가능)"

    # 구버전 결과 JSON 호환: 단위기간이 기록되지 않았으면 만기/스텝수로 산출
    step_years = vi.get("step_years") or (vi["maturity_years"] / vi["binomial_steps"])
    step_days = step_years * 365

    # ── 행사가격 서술: 옵션 대가율(보장수익률)이 있으면 시점별로 상승한다 ──
    growth = float(vi.get("strike_growth_rate", 0.0) or 0.0)
    if growth:
        strike_desc = (f"{krw(vi['strike_price_krw'])} 원 → 만기 시 "
                       f"{krw(vi.get('strike_at_maturity_krw', vi['strike_price_krw']))} 원")
        strike_growth_note = (
            f". 계약상 옵션 대가(보장수익률) 연 {pct(growth)}가 적용되어 행사가격은 "
            f"K(t) = 기준가 × (1 + {pct(growth)})^t 로 시점에 따라 복리 상승하며, "
            f"이항트리의 각 시점 노드에 해당 시점의 행사가격을 적용하였다"
        )
    else:
        strike_desc = f"{krw(vi['strike_price_krw'])} 원"
        strike_growth_note = "상 고정 행사가격으로, 만기까지 변동하지 않는다"

    rf_term_note = (
        "하였다. 또한 수익률곡선의 기간구조를 반영하기 위하여 현물이자율로부터 "
        "구간별 선도이자율(forward rate)을 도출하고, 이항트리의 각 스텝에 해당 구간의 "
        "선도이자율을 적용하여 위험중립확률과 할인을 산정하였다"
        if vi.get("discounting") == "term_structure"
        else "하였다"
    )

    vol_detail = vol.get("detail")
    if vol_detail:
        vol_detail_note = (
            f". 유사 상장기업(대용기업) {len(vol_detail['peers'])}개사의 "
            f"{vol_detail['period']['start']} ~ {vol_detail['period']['end']} 기간 "
            f"영업일 기준 일별 종가로부터 로그수익률의 표준편차를 산출하고, "
            f"연간 영업일수(√{vol_detail['trading_days']})를 적용하여 연 변동성으로 환산한 뒤 "
            f"산술평균하였다"
        )
    else:
        vol_detail_note = ""

    # 보고서 예시용 소규모 트리 (실제 평가는 vi['binomial_steps'] 스텝으로 수행)
    example_params = BinomialParams(
        s0=vi["underlying_price_krw"],
        sigma=vol["value"],
        rf=rf["value"],
        maturity=vi["maturity_years"],
        steps=EXAMPLE_TREE_STEPS,
        dividend_yield=vi["dividend_yield"],
    )
    example_step_years = vi["maturity_years"] / EXAMPLE_TREE_STEPS
    if growth:
        payoff = payoffs.call_with_schedule(
            payoffs.strike_schedule(
                vi["strike_price_krw"], growth, example_step_years, EXAMPLE_TREE_STEPS
            )
        )
    else:
        payoff = payoffs.call(vi["strike_price_krw"])
    american = vi["exercise_style"] != "european"
    stock_tree, _, value_tree = build_trees(example_params, payoff, american=american)

    today = date.today().isoformat()

    return f"""<!DOCTYPE html>
<html lang="ko">
<head><meta charset="utf-8"><title>파생상품 가치평가보고서</title><style>{CSS}</style></head>
<body>

<div class="cover">
  <div class="brand"><span class="bar"></span>Binomial Valuation Engine</div>
  <div class="mid">
    <div class="label">파생상품 가치평가 의견서</div>
    <div class="title">{esc(u['issuer'])}<br>콜옵션 가치평가보고서</div>
    <div class="subject">평가대상: {esc(u['issuer'])} {esc(u['security_type'])}에 대한 콜옵션<br>
    평가기준일: {esc(vi['valuation_date'])}</div>
  </div>
  <div class="bottom">
    <div class="date">{today}</div>
    {fictional_banner}
    <div class="disclaimer">
      본 보고서 및 평가결과는 평가기준일 현재, 본 보고서에 기술된 특정 목적만을 위하여 타당하다.
      본 보고서는 기술된 목적 외의 용도나 제3자의 어떠한 목적으로도 이용될 수 없으며, 어떠한
      형태로든 투자자문이 아니고 그렇게 해석되어서도 안 된다. 본 보고서의 어떠한 부분도 평가자의
      서면동의 없이 공중에 전파될 수 없다.
    </div>
  </div>
</div>

<div class="toc">
  <div class="toc-title">목 차</div>
  <ol>
    <li>Executive Summary
      <ol><li>가치평가방법</li><li>평가대상 거래 정보</li><li>평가결과</li><li>주요변수 및 가정</li></ol></li>
    <li>용역의 목적, 범위 및 한계
      <ol><li>용역의 목적</li><li>용역의 범위 및 수행절차</li><li>용역의 한계</li></ol></li>
    <li>파생상품 가치평가
      <ol><li>개요</li><li>CRR모형 가치평가방법</li><li>거래 조건</li><li>평가결과</li></ol></li>
  </ol>
</div>

<div class="chapter-head">
  <div class="chapter-num">01</div>
  <div class="chapter-title">Executive Summary</div>
</div>

<h3>1. 가치평가방법</h3>
<p>본 평가는 Cox-Ross-Rubinstein(1979) 이항모형(이하 "CRR모형")을 적용하여 콜옵션의
공정가치를 산정하였다. 트리 스텝 수는 {vi['binomial_steps']:,}개를 적용하였으며, 평가결과의
신뢰성 확보를 위하여 동일 가정 하의 몬테카를로 시뮬레이션으로 교차검증을 수행하였다.</p>

<h3>2. 평가대상 거래 정보</h3>
<table style='width: 85%'>
  <tr><th style='width: 32%'>계약명</th><td>{esc(c['contract_name'])}</td></tr>
  <tr><th>계약일</th><td>{esc(c['contract_date'])}</td></tr>
  <tr><th>투자자 (옵션 보유자)</th><td>{esc(c['investor'])}</td></tr>
  <tr><th>부여자 (거래상대방)</th><td>{esc(c['grantor'])}</td></tr>
  <tr><th>기초자산</th><td>{esc(u['issuer'])} {esc(u['security_type'])} ({esc(u['listing_status'])})</td></tr>
  <tr><th>대상주식수량</th><td class='num'>{r.get('total_shares', terms['quantity_shares']):,} 주</td></tr>
  <tr><th>행사범위 · 행사비율</th><td class='num'>{pct(r.get('exercise_scope', 1.0))} · {pct(r.get('allocation_ratio', 1.0))}</td></tr>
  <tr><th>콜옵션 수량</th><td class='num'><b>{r['quantity_shares']:,} 주</b></td></tr>
  <tr><th>행사가격</th><td class='num'>{strike_desc}</td></tr>
  <tr><th>거래종결일 (만기)</th><td>{esc(vi['maturity_date'])}</td></tr>
  <tr><th>행사방식</th><td>{style_label}</td></tr>
  <tr><th>결제방식</th><td>{esc(terms.get('settlement', '-'))}</td></tr>
</table>

<h3>3. 평가결과</h3>
<table style='width: 78%'>
  <tr><th style='width: 45%'>콜옵션 1주당 공정가치</th><td class='num'><b>{krw(r['unit_value_krw'], 2)} 원</b></td></tr>
  <tr><th>평가대상 콜옵션 수량</th><td class='num'>{r['quantity_shares']:,} 주</td></tr>
  <tr><th>총 평가액</th><td class='num'><b>{krw(r['total_value_krw'])} 원</b></td></tr>
  <tr><th>몬테카를로 교차검증</th><td>{'생략' if result['cross_check'].get('skipped') else ('합격 — 이항모형 평가액이 시뮬레이션 신뢰구간 내' if result['cross_check']['passed'] else '불합격')}</td></tr>
</table>
{_holders_table(r)}

<h3>4. 주요변수 및 가정</h3>
<p>본 평가에 적용한 주요변수의 정의와 적용 내역은 다음과 같다. 각 변수의 상세한 산출 근거는
제3장 및 별첨(산출 내역)에 기술하였다.</p>
<table>
  <tr><th style='width: 12%'>구분</th><th style='width: 22%'>내용</th><th>적용 내역</th></tr>
  <tr><td>S</td><td>기초자산 가액<br><span class="note">Current Stock Price</span></td>
      <td>{krw(vi['underlying_price_krw'])} 원 — {esc(u['listing_status'])} 주식으로서 평가자가
          합리적으로 추정한 평가기준일({esc(vi['valuation_date'])}) 현재 1주당 가액</td></tr>
  <tr><td>X</td><td>행사가격<br><span class="note">Exercise Price</span></td>
      <td>{strike_desc} — 계약서상 행사가격{strike_growth_note}</td></tr>
  <tr><td>T</td><td>잔존만기<br><span class="note">Maturity (Yr)</span></td>
      <td>{vi['maturity_years']:.4f} 년 — 평가기준일부터 거래종결일({esc(vi['maturity_date'])})까지의
          기간을 실제 일수 기준(ACT/365)으로 환산</td></tr>
  <tr><td>Rf</td><td>무위험이자율<br><span class="note">Risk Free Rate</span></td>
      <td>{pct(rf['value'], 4)} (연속복리) — 평가기준일 현재 국고채 만기수익률을 기초로
          부트스트래핑하여 현물이자율(spot rate) 곡선을 산출하고, 잔존만기에 해당하는 이자율을
          보간법으로 적용{rf_term_note}</td></tr>
  <tr><td>D</td><td>배당수익률<br><span class="note">Dividends</span></td>
      <td>{pct(vi['dividend_yield'])} — {'기초자산의 배당 정책을 반영하여 연속 배당수익률로 적용' if vi['dividend_yield'] > 0 else '평가대상 기초자산은 배당이 없는 것으로 가정'}</td></tr>
  <tr><td>σ</td><td>주가 변동성<br><span class="note">Volatility</span></td>
      <td>{pct(vol['value'])} (연환산) — {esc(vol['basis'])}{vol_detail_note}</td></tr>
</table>

<div class="chapter">
<div class="chapter-head">
  <div class="chapter-num">02</div>
  <div class="chapter-title">용역의 목적, 범위 및 한계</div>
</div>
</div>

<h3>1. 용역의 목적</h3>
<p>본 용역의 목적은 평가기준일({esc(vi['valuation_date'])}) 현재
{esc(c['governing_document'])}에 따라 {esc(c['investor'])}이 보유한
{esc(u['issuer'])} {esc(u['security_type'])}에 대한 콜옵션의 공정가치를 산정하는 것이다.
평가결과는 평가기준일 현재, 본 보고서에 기술된 목적만을 위하여 타당하다.</p>

<h3>2. 용역의 범위 및 수행절차</h3>
<ol>
  <li>계약서 검토 및 평가대상 거래 조건 확인</li>
  <li>가치평가 주요변수의 수집·추정 (변동성: 피어그룹 역사적 변동성, 무위험이자율: 국고채 spot rate)</li>
  <li>CRR 이항모형에 의한 콜옵션 공정가치 산정</li>
  <li>몬테카를로 시뮬레이션 교차검증 및 민감도 분석</li>
  <li>가치평가보고서 작성</li>
</ol>

<h3>3. 용역의 한계</h3>
<ul class="limits">
  <li>평가인은 평가과정에서 제공받은 재무정보와 기타 정보를 별도의 검증 없이 제공받은
      그대로 수용하였으며, 이들 정보에 대하여 감사, 검토 등 어떠한 형태의 인증도 표명하지
      아니한다. 제공받지 못한 정보나 제공받은 정보의 오류로 인해 평가결과가 달라질 수 있다.</li>
  <li>공공정보와 산업 및 통계자료(주가, 금리 등)는 신뢰할 수 있다고 판단한 원천에서
      입수하였으나, 그 정확성이나 완전성에 대하여 보증하지 아니한다.</li>
  <li>미래의 사건이나 상황은 예측과 달라질 수 있으며, 평가인은 예측성과의 달성에 대하여
      어떠한 확신도 제공하지 아니한다.</li>
  <li>본 보고서 및 평가결과는 기술된 특정 목적 전용이며, 목적 외 용도나 제3자의 어떠한
      목적으로도 이용될 수 없고, 투자자문이 아니며 그렇게 해석되어서도 안 된다.</li>
  <li>본 보고서의 어떠한 부분도 평가자의 서면동의 및 승인 없이 공중에 전파될 수 없다.</li>
</ul>

<div class="chapter">
<div class="chapter-head">
  <div class="chapter-num">03</div>
  <div class="chapter-title">파생상품 가치평가<br>
    <span class="chapter-sub">{esc(u['issuer'])} 보통주 콜옵션 — CRR 이항모형</span></div>
</div>
</div>

<h3>1. 개요</h3>
<p>평가대상은 {esc(u['issuer'])} {esc(u['security_type'])}를 기초자산으로 하는
{style_label} 콜옵션이다. 본 평가에서는 파생상품의 가치평가를 위하여
Cox-Ross-Rubinstein Model(이하 "CRR모형")을 사용하였다.</p>
<p>기초자산이 {esc(u['listing_status'])} 주식인 점을 고려하여, 주가 변동성은 유사 상장기업
(대용기업)의 역사적 변동성을 이용하여 추정하였으며, 무위험이자율은 평가기준일 현재
국고채 수익률로부터 산출한 현물이자율(spot rate)을 적용하였다. 평가결과의 신뢰성 확보를
위하여 동일한 가정 하에서 계산 구조가 상이한 몬테카를로 시뮬레이션으로 교차검증을 수행하였다.</p>

<h3>2. CRR모형 가치평가방법</h3>

<h4>2.1 CRR모형 가치평가방법론</h4>
<p>CRR모형은 Cox, J.C., Ross, S.A. and Rubinstein, M.이 1979년에 제시한 옵션가격결정모형으로,
블랙-숄즈 모형과 같은 연속시간모형(continuous-time model)이 아니라 이항트리(binomial tree)에서
단위 시간 간격마다 가능한 주가를 결정하고 옵션가치를 산출하는 이산시간모형(discrete-time model)이다.
CRR모형으로 파생상품을 평가하는 순서는, 우선 평가기준일로부터 만기일까지의 미래주가를
이항트리 내 단위 시간 간격마다 차례대로 추정한 후, 만기일로부터 단위 시간 간격마다
귀납적으로 역산하는 과정인 후방귀납법(backward induction)을 적용하여 추정된 미래 주가에
옵션의 가치를 계산하는 2단계 절차로 이루어진다.</p>
<p>이 모형에 의하면 옵션가격은 주가의 상승과 하락의 확률이나 투자자의 위험회피도, 다른 자산가치의
변동에 관계없이 객관적인 옵션의 가격을 계산해낼 수 있다. 즉, 이 모형은 평가방법이 직관적이며
다양한 파생상품의 평가에 응용이 가능하다는 장점을 가지고 있다.</p>

<h4>2.2 주가트리의 생성</h4>
<p>이 모형을 사용하기 위해서는 주가의 미래주가 추정이 필요하다. 이를 계산하기 위해서는
위험중립확률(Risk Neutral Probability, q)과 위험중립 상승비율(u), 하락비율(d)을 계산하여야 한다.
주가는 매 단위기간(Δt)마다 u배로 상승하거나 d배로 하락하며, 상승·하락 배수는 기초자산의
변동성(σ)에 의해 결정된다.</p>
<div class="formula">
u = exp(σ·√Δt) = {example_params.u:.6f}<br>
d = 1 / u = {example_params.d:.6f}<br>
q = (a − d) / (u − d),&nbsp;&nbsp; a = 위험중립 성장배수 {'(스텝별 선도이자율 기준)' if vi.get('discounting') == 'term_structure' else '= exp((r − δ)·Δt)'}<br>
할인계수 = {'1 / (1 + f_i)   (스텝별 선도이자율)' if vi.get('discounting') == 'term_structure' else 'exp(−r·Δt)'}
</div>
<p>위 수치는 예시 표시용 {EXAMPLE_TREE_STEPS}스텝 기준이며, 실제 평가에는
{vi['binomial_steps']:,}스텝(단위기간 {step_days:.1f}일)을 적용하였다.
d = 1/u 로 설정함으로써 상승 후 하락한 노드와 하락 후 상승한 노드의 주가가 일치하여
트리가 재결합(recombining)하므로, 노드 수가 기간에 대해 선형으로 증가하여 계산 효율이 확보된다.</p>

<h4>2.3 후방귀납법(Backward Induction)에 의한 옵션가치 산출</h4>
<p>후방귀납법은 만기일로부터 역순대로 시점 및 노드별 산출된 주가에서 파생상품 가치를 계산하는
과정이다. 시점 t, 노드 j의 주가를 S(t, j)로 표기할 때, 만기 시점 T의 각 노드에서 옵션의 가치는
행사가격 K에 대하여 max(S(T, j) − K, 0)이다.</p>
<p>만기 직전 시점 T−1의 노드에서는 투자자가 행사를 할 수도 있지만, 미래의 파생상품 가치가
더 높다고 판단한다면 행사하지 않고 파생상품을 보유할 수도 있다. 따라서 행사 시 가치와 보유 시
기대가치를 서로 비교하여 더 높은 가치가 해당 노드의 옵션 가치가 되며, 보유 시 기대가치는
직후 시점 인접하는 두 노드의 파생상품 가치를 토대로 계산할 수 있다. 즉, 인접한 두 노드의
파생상품 가치가 각각 위험중립확률로 가중평균된 후 단위기간의 무위험이자율(또는 해당 구간의
선도이자율)로 할인된 값이 보유 시 기대가치가 된다. 이러한 기대가치와 행사가치 중 큰 금액이
해당 노드의 파생상품 가치가 된다.</p>
<div class="formula">
V(t, j) = max[ 행사가치, 보유가치 ]<br>
&nbsp;&nbsp;행사가치 = max(S(t, j) − K(t), 0)<br>
&nbsp;&nbsp;보유가치 = 할인계수 × [ q · V(t+1, j+1) + (1 − q) · V(t+1, j) ]
</div>
<p>평가기준일 시점까지 이 과정을 귀납적으로 반복하여 최종적으로 산출되는 t=0 노드의 금액이
파생상품의 공정가치가 된다.{
' 유럽형 옵션은 만기에만 행사가 가능하므로 각 노드에서 행사가치와의 비교 없이 보유가치만으로 역산한다.'
if vi['exercise_style'] == 'european'
else ' 미국형 옵션은 기간 중 언제든 행사가 가능하므로 모든 노드에서 행사가치와 보유가치를 비교한다.'
}</p>

<h4>2.4 투입변수</h4>
<p><b>(1) Node 주기</b><br>
CRR모형을 적용함에 있어 노드 주기는 {step_days:.1f}일
({'1주일' if vi.get('step_unit') == 'weekly' else f"잔존만기를 {vi['binomial_steps']:,}등분"})을
기본적으로 적용하였다. 노드 주기를 짧게 할수록 평가결과는 연속시간모형의 해석해에 수렴한다.</p>
<p><b>(2) 무위험이자율</b><br>
무위험이자율은 평가기준일 현재 공시된 국고채 만기수익률을 기초로 산출하였다. 평가기준일 현재
평가대상의 잔존만기와 동일한 만기가 없는 경우에는 잔존만기에 해당하는 이자율을 보간법으로
산출하여 적용하였다. 만기수익률(YTM)은 이표 재투자를 전제한 수익률이므로, 이를 그대로 할인율로
사용하지 않고 부트스트래핑을 통해 현물이자율(spot rate)로 전환하여 적용하였다.
{'또한 수익률곡선의 기간구조를 반영하기 위하여 현물이자율로부터 구간별 선도이자율(forward rate)을 도출하고, 트리의 각 스텝에 해당 구간의 선도이자율을 적용하였다.' if vi.get('discounting') == 'term_structure' else ''}</p>
<p><b>(3) 배당률</b><br>
{'기초자산의 배당수익률 ' + pct(vi['dividend_yield']) + '를 위험중립 성장배수에 반영하였다.' if vi['dividend_yield'] > 0 else '평가대상 기초자산은 배당이 없는 것으로 가정하였다.'}</p>
<p><b>(4) 주가변동성</b><br>
유사 상장회사(대용기업)의 주가를 기초로 평가기준일 기준 일별 로그수익률의 표준편차를 산출한 후,
연간 영업일수를 적용하여 연 주가변동성을 산출하였다. 상기와 같이 산출된 연 주가변동성을
Node 주기별로 환산하여 적용하였다.</p>
{'<p><b>(5) 행사가격</b><br>계약상 옵션 대가(보장수익률) 연 ' + pct(growth) + '가 적용되어 행사가격이 시점에 따라 복리로 상승하는 구조이므로, 고정 행사가격이 아닌 시점별 행사가격 스케줄 K(t) = 기준가 × (1 + 대가율)^t 을 이항트리의 각 시점 노드에 적용하였다.</p>' if growth else ''}

<h3>3. 거래 조건</h3>
<p>{esc(c['contract_date'])} 체결된 {esc(c['contract_name'])}에 따라 {esc(c['investor'])}은
{esc(u['issuer'])} {esc(u['security_type'])}에 대한 콜옵션을 보유한다. 계약상 대상주식수량
{r.get('total_shares', 0):,}주 중 행사범위 {pct(r.get('exercise_scope', 1.0))}에 해당하는
{r.get('scoped_shares', 0):,}주가 콜옵션 행사 대상이며,
{'이를 아래 보유자별 행사비율에 따라 배분한 결과 평가대상 콜옵션 수량은 ' if len(r.get('holders', [])) >= 2 else '그중 평가대상 보유자의 행사비율은 ' + pct(r.get('allocation_ratio', 1.0)) + '로서 평가대상 콜옵션 수량은 '}<b>{r['quantity_shares']:,}주</b>이다.</p>
<p>행사가격은 1주당 {strike_desc}이며, 행사방식은 {style_label}, 결제는
{esc(terms.get('settlement', '-'))} 방식이다. 거래종결일은 {esc(vi['maturity_date'])}로서
평가기준일 현재 잔존만기는 {vi['maturity_years']:.4f}년이다.</p>

<h3>4. 평가결과</h3>
<p>CRR모형({vi['binomial_steps']:,}스텝, 단위기간 {step_days:.1f}일)에 의한
콜옵션의 공정가치는 1주당 <b>{krw(r['unit_value_krw'], 2)}원</b>으로 산정되었으며,
평가대상 콜옵션 수량 {r['quantity_shares']:,}주를 적용한 총 평가액은
<b>{krw(r['total_value_krw'])}원</b>이다.</p>
{_holders_table(r)}

<h4>가. 이항트리 구조 (예시: {EXAMPLE_TREE_STEPS}스텝)</h4>
{_tree_table(stock_tree, f"주가 트리 (원) — 행 u×j는 상승 j회 노드, 열 t는 경과 스텝")}
{_tree_table(value_tree, "콜옵션 가치 트리 (원)")}

<h4>나. 몬테카를로 교차검증</h4>
{_cross_check_section(result['cross_check'])}

<h4>다. 민감도 분석</h4>
<p>주요변수 변동이 평가액에 미치는 영향은 다음과 같다.</p>
{_sensitivity_table(result['sensitivity'], r['unit_value_krw'])}

{_volatility_rows(vol)}
{_risk_free_rows(rf)}

<p class="note" style="margin-top: 10mm">
본 보고서는 CRR 이항모형 평가 엔진(결과 JSON: {esc(result['meta']['run_at'])} 실행)의
계산 결과만을 사용하여 작성되었다.
{'본 보고서는 검증용 가상 데이터 기반이며 실제 거래·실존 회사와 무관하다.' if is_fictional else ''}
</p>

</body>
</html>"""


def find_browser() -> str | None:
    """PDF 변환에 사용할 Edge/Chrome/Chromium 실행 파일을 찾는다."""
    for candidate in BROWSER_CANDIDATES:  # 윈도우 고정 경로
        if Path(candidate).exists():
            return candidate
    for command in BROWSER_COMMANDS:  # PATH 탐색 (리눅스 배포 환경)
        found = shutil.which(command)
        if found:
            return found
    return None


def html_to_pdf(html_path: Path, pdf_path: Path) -> None:
    """Edge/Chrome headless 인쇄 기능으로 HTML을 PDF로 변환한다."""
    browser = find_browser()
    if browser is None:
        raise RuntimeError(
            "PDF 변환에 사용할 Edge 또는 Chrome을 찾지 못했습니다. "
            f"HTML 보고서는 생성되었습니다: {html_path}"
        )
    args = [
        browser,
        "--headless",
        "--disable-gpu",
        "--no-pdf-header-footer",
        f"--print-to-pdf={pdf_path.resolve()}",
        html_path.resolve().as_uri(),
    ]
    if os.name != "nt":
        # 컨테이너(배포 환경)에서는 샌드박스를 비활성화해야 chromium이 기동된다
        args[1:1] = ["--no-sandbox", "--disable-dev-shm-usage"]
    subprocess.run(args, check=True, timeout=120, capture_output=True)
    if not pdf_path.exists():
        raise RuntimeError("PDF 파일이 생성되지 않았습니다.")


def generate_report(
    contract_path, result_path, output_dir, html_only: bool = False
) -> Path:
    """보고서를 생성하고 산출 파일 경로를 반환한다 (PDF 또는 --html-only 시 HTML)."""
    contract = json.loads(Path(contract_path).read_text(encoding="utf-8"))
    result = json.loads(Path(result_path).read_text(encoding="utf-8"))

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 파일명은 URL 인코딩 문제가 없도록 영문 사용 (발행회사명 등은 보고서 본문에 표기)
    valuation_date = result["valuation_inputs"]["valuation_date"]
    stem = f"valuation-report_{valuation_date}"

    html_path = out_dir / f"{stem}.html"
    html_path.write_text(build_report_html(contract, result), encoding="utf-8")
    if html_only:
        return html_path

    pdf_path = out_dir / f"{stem}.pdf"
    html_to_pdf(html_path, pdf_path)
    html_path.unlink()  # 중간 산출물 정리 (최종 산출물은 PDF)
    return pdf_path


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="평가보고서 PDF 생성")
    parser.add_argument("--contract", required=True, help="계약정보 JSON 경로")
    parser.add_argument("--result", required=True, help="run_valuation 결과 JSON 경로")
    parser.add_argument("--output-dir", default="reports", help="보고서 저장 디렉토리")
    parser.add_argument("--html-only", action="store_true", help="PDF 변환 없이 HTML만 생성")
    args = parser.parse_args(argv)

    out_path = generate_report(args.contract, args.result, args.output_dir, args.html_only)
    print(f"보고서 생성 완료: {out_path}")


if __name__ == "__main__":
    main()
