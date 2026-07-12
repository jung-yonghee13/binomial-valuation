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
import subprocess
from datetime import date
from pathlib import Path

import numpy as np

from valuation import payoffs
from valuation.binomial import BinomialParams, build_trees

EXAMPLE_TREE_STEPS = 5

BROWSER_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]

CSS = """
@page { size: A4; margin: 22mm 18mm; }
* { box-sizing: border-box; }
body {
  font-family: 'Malgun Gothic', '맑은 고딕', sans-serif;
  font-size: 10.5pt; line-height: 1.65; color: #1a1a1a; margin: 0;
}
h1 { font-size: 17pt; margin: 0 0 4mm; }
h2 { font-size: 13.5pt; border-bottom: 2px solid #2c3e60; padding-bottom: 2mm;
     margin: 10mm 0 5mm; color: #2c3e60; page-break-after: avoid; }
h3 { font-size: 11.5pt; margin: 7mm 0 3mm; color: #2c3e60; page-break-after: avoid; }
table { border-collapse: collapse; width: 100%; margin: 3mm 0 5mm; page-break-inside: avoid; }
th, td { border: 1px solid #b8bfcc; padding: 1.6mm 2.5mm; font-size: 9.5pt; }
th { background: #eef1f7; font-weight: 600; text-align: left; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
.tree td, .tree th { text-align: right; font-size: 8.5pt; padding: 1.2mm 1.8mm; }
.cover { text-align: center; padding-top: 55mm; page-break-after: always; }
.cover .title { font-size: 24pt; font-weight: 700; margin-bottom: 12mm; }
.cover .subject { font-size: 13pt; margin: 3mm 0; }
.cover .fictional {
  display: inline-block; margin-top: 18mm; padding: 3mm 8mm;
  border: 2px solid #b03030; color: #b03030; font-weight: 700; font-size: 12pt;
}
.cover .disclaimer { margin-top: 25mm; font-size: 9pt; color: #555;
  text-align: left; border: 1px solid #ccc; padding: 4mm; }
.toc { page-break-after: always; }
.toc ol { line-height: 2.1; }
.chapter { page-break-before: always; }
.passfail-pass { color: #1a7a2e; font-weight: 700; }
.passfail-fail { color: #b03030; font-weight: 700; }
.note { font-size: 9pt; color: #555; }
.formula { background: #f5f6fa; border: 1px solid #d8dce6; padding: 3mm 5mm;
  font-family: Consolas, monospace; font-size: 9.5pt; margin: 3mm 0; }
ul.limits li { margin-bottom: 2mm; }
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
       출처: {esc(detail.get('curve_source') or 'KOFIA 채권정보센터')}) 에서
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

    # 보고서 예시용 소규모 트리 (실제 평가는 vi['binomial_steps'] 스텝으로 수행)
    example_params = BinomialParams(
        s0=vi["underlying_price_krw"],
        sigma=vol["value"],
        rf=rf["value"],
        maturity=vi["maturity_years"],
        steps=EXAMPLE_TREE_STEPS,
        dividend_yield=vi["dividend_yield"],
    )
    payoff = payoffs.call(vi["strike_price_krw"])
    american = vi["exercise_style"] != "european"
    stock_tree, _, value_tree = build_trees(example_params, payoff, american=american)

    today = date.today().isoformat()

    return f"""<!DOCTYPE html>
<html lang="ko">
<head><meta charset="utf-8"><title>파생상품 가치평가보고서</title><style>{CSS}</style></head>
<body>

<div class="cover">
  <div class="title">파생상품(콜옵션)<br>가치평가보고서</div>
  <div class="subject">평가대상: {esc(u['issuer'])} {esc(u['security_type'])}에 대한 콜옵션</div>
  <div class="subject">평가기준일: {esc(vi['valuation_date'])}</div>
  <div class="subject">보고서 작성일: {today}</div>
  {fictional_banner}
  <div class="disclaimer">
    본 보고서 및 평가결과는 평가기준일 현재, 본 보고서에 기술된 특정 목적만을 위하여 타당하다.
    본 보고서는 기술된 목적 외의 용도나 제3자의 어떠한 목적으로도 이용될 수 없으며, 어떠한
    형태로든 투자자문이 아니고 그렇게 해석되어서도 안 된다. 본 보고서의 어떠한 부분도 평가자의
    서면동의 없이 공중에 전파될 수 없다.
  </div>
</div>

<div class="toc">
  <h1>목 차</h1>
  <ol>
    <li>제1장 Executive Summary
      <ol><li>가치평가방법</li><li>평가대상 거래 정보</li><li>평가결과</li><li>주요변수 및 가정</li></ol></li>
    <li>제2장 용역의 목적, 범위 및 한계
      <ol><li>용역의 목적</li><li>용역의 범위 및 수행절차</li><li>용역의 한계</li></ol></li>
    <li>제3장 파생상품 가치평가
      <ol><li>개요</li><li>CRR모형 가치평가방법</li><li>거래 조건</li><li>평가결과</li></ol></li>
  </ol>
</div>

<h2>제1장 Executive Summary</h2>

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
  <tr><th>대상주식수량</th><td class='num'>{int(terms['quantity_shares']):,} 주</td></tr>
  <tr><th>행사가격</th><td class='num'>{krw(vi['strike_price_krw'])} 원</td></tr>
  <tr><th>거래종결일 (만기)</th><td>{esc(vi['maturity_date'])}</td></tr>
  <tr><th>행사방식</th><td>{style_label}</td></tr>
  <tr><th>결제방식</th><td>{esc(terms.get('settlement', '-'))}</td></tr>
</table>

<h3>3. 평가결과</h3>
<table style='width: 70%'>
  <tr><th>콜옵션 1주당 공정가치</th><td class='num'><b>{krw(r['unit_value_krw'], 2)} 원</b></td></tr>
  <tr><th>총 평가액 ({r['quantity_shares']:,}주)</th><td class='num'><b>{krw(r['total_value_krw'])} 원</b></td></tr>
  <tr><th>몬테카를로 교차검증</th><td>{'생략' if result['cross_check'].get('skipped') else ('합격' if result['cross_check']['passed'] else '불합격')}</td></tr>
</table>

<h3>4. 주요변수 및 가정</h3>
<table>
  <tr><th>변수</th><th class='num'>적용 값</th><th>산출 근거</th></tr>
  <tr><td>평가기준일</td><td class='num'>{esc(vi['valuation_date'])}</td><td>평가 계약에 따름</td></tr>
  <tr><td>기초자산 가액</td><td class='num'>{krw(vi['underlying_price_krw'])} 원</td><td>평가자 추정 투입</td></tr>
  <tr><td>행사가격</td><td class='num'>{krw(vi['strike_price_krw'])} 원</td><td>계약서</td></tr>
  <tr><td>잔존만기</td><td class='num'>{vi['maturity_years']:.4f} 년</td><td>평가기준일 ~ 거래종결일 (ACT/365)</td></tr>
  <tr><td>주가 변동성</td><td class='num'>{pct(vol['value'])}</td><td>{esc(vol['basis'])}</td></tr>
  <tr><td>무위험이자율</td><td class='num'>{pct(rf['value'], 4)}</td><td>{esc(rf['basis'])}</td></tr>
  <tr><td>배당수익률</td><td class='num'>{pct(vi['dividend_yield'])}</td><td>기초자산 배당 정책 반영</td></tr>
</table>

<h2 class="chapter">제2장 용역의 목적, 범위 및 한계</h2>

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

<h2 class="chapter">제3장 파생상품 가치평가</h2>

<h3>1. 개요</h3>
<p>평가대상은 {esc(u['issuer'])} {esc(u['security_type'])}를 기초자산으로 하는
{style_label} 콜옵션이다. 기초자산이 {esc(u['listing_status'])} 주식이므로 변동성은
유사 상장기업(피어그룹)의 역사적 변동성을 이용하여 추정하였다.</p>

<h3>2. CRR모형 가치평가방법</h3>
<p>CRR모형은 기초자산 주가가 매 단위기간(Δt)마다 일정 배수로 상승(u)하거나 하락(d)한다고
가정하고, 위험중립확률(q)로 만기 페이오프의 기대값을 역방향으로 할인하여 현재가치를
산정한다. 위험중립확률과 할인계수는 동일한 연속복리 기준을 적용하였다.</p>
<div class="formula">
u = exp(σ·√Δt) = {example_params.u:.6f} (Δt = 잔존만기/스텝수 기준)<br>
d = 1/u = {example_params.d:.6f}<br>
q = (exp((r−δ)·Δt) − d) / (u − d)<br>
할인계수 = exp(−r·Δt)
</div>
<p class="note">위 수치는 예시 표시용 {EXAMPLE_TREE_STEPS}스텝 기준이며, 실제 평가에는
{vi['binomial_steps']:,}스텝을 적용하였다. 스텝 수 증가에 따라 평가액은 Black-Scholes
해석해에 수렴하며, 본 엔진은 해석해 수렴·풋-콜 패리티 자동 테스트로 상시 검증된다.</p>

<h3>3. 거래 조건</h3>
<p>{esc(c['contract_date'])} 체결된 {esc(c['contract_name'])}에 따라 {esc(c['investor'])}은
{esc(u['issuer'])} {esc(u['security_type'])} {int(terms['quantity_shares']):,}주를 1주당
{krw(vi['strike_price_krw'])}원에 매수할 수 있는 권리를 보유한다. 행사방식은 {style_label}이며,
결제는 {esc(terms.get('settlement', '-'))} 방식이다.</p>

<h3>4. 평가결과</h3>
<p>CRR모형({vi['binomial_steps']:,}스텝)에 의한 콜옵션 공정가치는 1주당
<b>{krw(r['unit_value_krw'], 2)}원</b>, 대상주식수량 {r['quantity_shares']:,}주 기준 총
<b>{krw(r['total_value_krw'])}원</b>으로 산정되었다.</p>

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
    """PDF 변환에 사용할 Edge/Chrome 실행 파일을 찾는다."""
    for candidate in BROWSER_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return None


def html_to_pdf(html_path: Path, pdf_path: Path) -> None:
    """Edge/Chrome headless 인쇄 기능으로 HTML을 PDF로 변환한다."""
    browser = find_browser()
    if browser is None:
        raise RuntimeError(
            "PDF 변환에 사용할 Edge 또는 Chrome을 찾지 못했습니다. "
            f"HTML 보고서는 생성되었습니다: {html_path}"
        )
    subprocess.run(
        [
            browser,
            "--headless",
            "--disable-gpu",
            "--no-pdf-header-footer",
            f"--print-to-pdf={pdf_path.resolve()}",
            html_path.resolve().as_uri(),
        ],
        check=True,
        timeout=120,
        capture_output=True,
    )
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

    valuation_date = result["valuation_inputs"]["valuation_date"]
    issuer = contract["underlying"]["issuer"].replace(" ", "")
    stem = f"평가보고서_{valuation_date}_{issuer}"

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
