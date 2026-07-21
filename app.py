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

from valuation import krx_lookup
from valuation import report as report_module
from valuation import run_valuation

ROOT = Path(__file__).parent
ACCENT = "#E8490F"  # 포인트 컬러 (보고서 오렌지 계열)
APP_BUILD = "2026-07-21.1"  # 배포 버전 확인용 (푸시 시 갱신)

st.set_page_config(
    page_title="이항모형 가치평가",
    page_icon=str(ROOT / "assets" / "favicon.png"),  # 이항트리 로고 (assets/favicon.png)
    layout="wide",
)

# ══════════════════════════════════════════════════════════════════════
#  Valuation Suite 디자인 시스템 (design-system.md 토큰만 사용)
#  — 색·간격·라운드·폰트는 아래 단일 <style> 블록의 CSS 변수로만 관리 —
# ══════════════════════════════════════════════════════════════════════
st.markdown(
    """
    <style>
    :root{
      /* 배경/표면 */
      --bg:#F6F4EF; --surface:#FFFFFF; --ink:#17150F; --ink-soft:#262117;
      /* 텍스트 */
      --text:#1E1B16; --text-mut:#8B857A; --text-inv:#F6F4EF;
      /* 포인트 */
      --accent:#E8490F; --accent-2:#F2A03D; --success:#3BA55D;
      /* 선/그림자 */
      --line:#EBE7DE; --node-out:#C9C2B4;
      --shadow:0 1px 2px rgba(23,21,15,.04), 0 8px 24px rgba(23,21,15,.06);
      --glow:0 0 0 1px rgba(232,73,15,.15), 0 12px 40px rgba(232,73,15,.18);
      /* 형태 */
      --r-card:16px; --r-tile:12px; --r-pill:999px; --pad-card:20px; --gap:16px;
    }
    .stApp{ background:var(--bg); }
    header[data-testid="stHeader"]{ background:transparent; }
    .block-container{ padding-top:.8rem; max-width:1500px; }
    html, body, [class*="css"]{
      font-family:"Pretendard","Noto Sans KR",-apple-system,"Segoe UI",Roboto,sans-serif;
    }
    .vs-num{ font-variant-numeric:tabular-nums; }

    /* 기본 크롬 숨김 (메뉴·푸터·deploy·소유자 배지) */
    #MainMenu, footer, [data-testid="stToolbar"],
    [class*="viewerBadge"], [data-testid="appCreatorAvatar"],
    .stAppDeployButton{ display:none !important; }

    /* ── 네비 레일 (다크 사이드바) ── */
    [data-testid="stSidebar"]{ background:var(--ink); border-right:1px solid #000; }
    [data-testid="stSidebar"] *{ color:var(--text-inv); }
    [data-testid="stSidebarUserContent"]{ padding-top:1.1rem; }
    .vs-brand{ display:flex; align-items:center; gap:10px; padding:2px 4px 14px 4px;
      border-bottom:1px solid rgba(246,244,239,.10); margin-bottom:12px; }
    .vs-logo{ width:30px; height:30px; background:var(--accent); border-radius:8px;
      transform:rotate(45deg); box-shadow:0 4px 14px rgba(232,73,15,.45); flex:0 0 auto; }
    .vs-brand-name{ font-size:15px; font-weight:700; line-height:1.1; }
    .vs-brand-sub{ font-size:10px; letter-spacing:.10em; text-transform:uppercase;
      color:rgba(246,244,239,.45); margin-top:2px; }
    .vs-nav-item{ display:flex; align-items:center; gap:10px; padding:9px 12px;
      border-radius:10px; font-size:13.5px; color:rgba(246,244,239,.72);
      margin:2px 0; border-left:3px solid transparent; }
    .vs-nav-item .ic{ width:16px; text-align:center; opacity:.85; }
    .vs-nav-item.active{ background:var(--ink-soft); color:var(--accent);
      border-left:3px solid var(--accent); font-weight:600; }
    .vs-status{ display:inline-flex; align-items:center; gap:8px; margin-top:14px;
      padding:7px 14px; border-radius:var(--r-pill); background:var(--ink-soft);
      font-size:11.5px; color:rgba(246,244,239,.80); }
    .vs-dot{ width:8px; height:8px; border-radius:50%; background:var(--success);
      box-shadow:0 0 0 3px rgba(59,165,93,.22); }

    /* ── 상단 바 ── */
    .vs-topbar{ display:flex; align-items:center; justify-content:space-between;
      gap:16px; padding:10px 4px 16px 4px; flex-wrap:wrap; }
    .vs-crumb{ font-size:13px; color:var(--text-mut); font-weight:500; }
    .vs-crumb b{ color:var(--text); font-weight:700; }
    .vs-crumb .sep{ margin:0 8px; opacity:.55; }
    .vs-top-right{ display:flex; align-items:center; gap:12px; flex-wrap:wrap; }
    .vs-search{ display:flex; align-items:center; gap:8px; padding:7px 14px;
      background:var(--surface); border:1px solid var(--line); border-radius:var(--r-pill);
      color:var(--text-mut); font-size:12.5px; min-width:150px; }
    .vs-export{ padding:8px 16px; background:var(--accent); color:#fff; font-weight:600;
      font-size:12.5px; border-radius:var(--r-pill); box-shadow:0 4px 12px rgba(232,73,15,.25); }
    .vs-avatar{ width:34px; height:34px; border-radius:50%; background:var(--ink);
      color:var(--text-inv); display:flex; align-items:center; justify-content:center;
      font-size:12.5px; font-weight:700; flex:0 0 auto; }
    .vs-runat{ font-size:11px; color:var(--text-mut); text-align:right; line-height:1.35; }

    /* ── 히어로 결과카드 (다크 + 오렌지 글로우) ── */
    .vs-hero{ position:relative; background:var(--ink); color:var(--text-inv);
      border-radius:var(--r-card); padding:26px 28px; box-shadow:var(--glow);
      background-image:radial-gradient(120% 90% at 0% 0%, rgba(242,160,61,.20), transparent 58%);
      overflow:hidden; }
    .vs-hero-label{ font-size:12px; letter-spacing:.06em; text-transform:uppercase;
      color:rgba(246,244,239,.55); }
    .vs-hero-value{ font-size:46px; font-weight:700; line-height:1.05; margin:8px 0 6px 0;
      font-variant-numeric:tabular-nums; }
    .vs-hero-value small{ font-size:20px; font-weight:600; color:rgba(246,244,239,.65);
      margin-left:6px; }
    .vs-hero-sub{ font-size:14px; color:var(--accent-2); font-weight:600;
      font-variant-numeric:tabular-nums; }
    .vs-hero-badge{ position:absolute; top:22px; right:24px; font-size:12px;
      font-weight:600; padding:5px 13px; border-radius:var(--r-pill); }
    .vs-badge-ok{ background:rgba(59,165,93,.16); color:#7FD69A; }
    .vs-badge-wait{ background:rgba(246,244,239,.10); color:rgba(246,244,239,.60); }

    /* ── KPI 스탯 타일 ── */
    .vs-kpirow{ display:flex; gap:var(--gap); margin-top:var(--gap); flex-wrap:wrap; }
    .vs-tile{ flex:1 1 160px; background:var(--surface); border-radius:var(--r-tile);
      padding:16px 18px; box-shadow:var(--shadow); border:1px solid var(--line); }
    .vs-tile .lab{ color:var(--text-mut); font-size:11.5px; letter-spacing:.04em;
      text-transform:uppercase; }
    .vs-tile .val{ font-size:25px; font-weight:700; color:var(--text); margin-top:4px;
      font-variant-numeric:tabular-nums; }
    .vs-tile .sub{ color:var(--text-mut); font-size:11.5px; margin-top:2px; }
    .vs-tile .val.ok{ color:var(--success); }

    /* ── 입력 변수 표 ── */
    .vs-vartable{ width:100%; border-collapse:collapse; font-size:13px; }
    .vs-vartable td{ padding:8px 4px; border-bottom:1px solid var(--line); }
    .vs-vartable tr:last-child td{ border-bottom:none; }
    .vs-vartable .sym{ color:var(--accent); font-weight:700; width:38px;
      font-family:"Cambria Math",Georgia,serif; }
    .vs-vartable .lab{ color:var(--text-mut); }
    .vs-vartable .val{ text-align:right; font-weight:600; color:var(--text);
      font-variant-numeric:tabular-nums; white-space:nowrap; }

    /* ── 모형 파라미터 칩 (Greeks 칩 컴포넌트 재사용) ── */
    .vs-chips{ display:grid; grid-template-columns:1fr 1fr; gap:10px; }
    .vs-chip{ display:flex; align-items:center; gap:10px; padding:9px 11px;
      background:rgba(232,73,15,.06); border:1px solid rgba(232,73,15,.14);
      border-radius:12px; }
    .vs-chip .g{ width:28px; height:28px; border-radius:8px; background:rgba(232,73,15,.14);
      color:var(--accent); display:flex; align-items:center; justify-content:center;
      font-weight:700; font-size:14px; font-family:"Cambria Math",Georgia,serif; flex:0 0 auto; }
    .vs-chip .g-name{ font-size:11px; color:var(--text-mut); line-height:1.2; }
    .vs-chip .g-val{ font-size:14px; font-weight:700; color:var(--text);
      font-variant-numeric:tabular-nums; }

    /* ── 격자 컨테이너 (좁은 화면 가로 스크롤 허용) ── */
    .vs-lattice-wrap{ overflow-x:auto; }
    .vs-legend{ display:flex; gap:16px; font-size:11.5px; color:var(--text-mut);
      margin-top:8px; }
    .vs-legend span{ display:inline-flex; align-items:center; gap:6px; }
    .vs-lg-fill{ width:11px; height:11px; border-radius:50%; background:var(--accent); }
    .vs-lg-out{ width:11px; height:11px; border-radius:50%; background:#fff;
      border:1.6px solid var(--node-out); }

    .vs-section{ font-size:15px; font-weight:600; color:var(--text); margin:2px 0 10px 0; }
    .vs-note{ font-size:11.5px; color:var(--text-mut); }

    /* ── 카드형 컨테이너 (입력 섹션) ── */
    div[data-testid="stVerticalBlockBorderWrapper"]{
      background:var(--surface); border:1px solid var(--line);
      border-radius:var(--r-card); box-shadow:var(--shadow);
      padding:.5rem 1rem .8rem 1rem;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] h3{
      color:var(--text); font-size:1.05rem; padding-top:.35rem; font-weight:700;
      border-bottom:1px solid var(--line); padding-bottom:.45rem;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] h3 .num{
      color:var(--accent); font-size:.82rem; font-weight:700; margin-right:.55rem;
      background:rgba(232,73,15,.10); padding:3px 9px; border-radius:var(--r-pill);
      vertical-align:.12rem; letter-spacing:.04em;
    }

    /* ── 입력 위젯: 흰 표면 + 헤어라인, 포커스 오렌지 ── */
    div[data-baseweb="input"], div[data-baseweb="select"] > div,
    div[data-baseweb="base-input"]{
      background:var(--surface) !important; border:1px solid var(--line) !important;
      border-radius:10px !important; transition:border-color .15s ease, box-shadow .15s ease;
    }
    div[data-baseweb="input"]:hover, div[data-baseweb="select"] > div:hover{
      border-color:var(--node-out) !important;
    }
    div[data-baseweb="input"]:focus-within, div[data-baseweb="select"] > div:focus-within{
      border-color:var(--accent) !important;
      box-shadow:0 0 0 3px rgba(232,73,15,.13) !important;
    }
    div[data-baseweb="input"] input, div[data-baseweb="base-input"] input{
      background:transparent !important;
    }
    div[data-testid="stNumberInputStepUp"], div[data-testid="stNumberInputStepDown"]{
      background:#FBF7F1; border-left:1px solid var(--line);
    }
    div[data-testid="stFileUploaderDropzone"]{
      background:#FBF7F1; border:1.5px dashed var(--accent-2); border-radius:12px;
    }
    div[data-testid="stDataFrame"], div[data-testid="stDataEditor"]{
      border:1px solid var(--line); border-radius:10px; overflow:hidden;
    }

    /* 버튼: 오렌지 필 */
    .stButton > button, .stDownloadButton > button{
      border-radius:12px; font-weight:600; padding:.55rem 1rem; border:1px solid var(--line);
    }
    .stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"]{
      background:var(--accent); border:none; color:#fff;
      box-shadow:0 4px 12px rgba(232,73,15,.25);
    }
    .stButton > button[kind="primary"]:hover,
    .stDownloadButton > button[kind="primary"]:hover{ background:#C93E0C; }

    /* 탭 강조 */
    button[data-baseweb="tab"]{ font-size:13px; }
    [data-baseweb="tab-highlight"]{ background:var(--accent) !important; }

    /* 지표 타일 (탭 내부 잔여용) */
    div[data-testid="stMetric"]{
      background:var(--surface); border:1px solid var(--line); border-radius:var(--r-tile);
      padding:.6rem .9rem;
    }
    div[data-testid="stMetricValue"]{ color:var(--accent); font-weight:700; font-size:1.4rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ──────────────────────────────────────────────────────────────────────
#  프레젠테이션 헬퍼 (반복 마크업은 함수로, 토큰은 CSS 변수로만)
# ──────────────────────────────────────────────────────────────────────
def _won(x: float, dec: int = 0) -> str:
    return f"{x:,.{dec}f}"


def render_sidebar() -> None:
    """좌측 다크 네비 레일: 브랜드 + 메뉴 + 하단 상태 pill."""
    nav = [
        ("▶", "평가 실행", True), ("▦", "대시보드", False),
        ("∿", "평가모형", False), ("⑃", "시나리오", False),
        ("▤", "리포트", False), ("◈", "데이터", False),
    ]
    items = "".join(
        f'<div class="vs-nav-item{" active" if act else ""}">'
        f'<span class="ic">{ic}</span><span>{lab}</span></div>'
        for ic, lab, act in nav
    )
    with st.sidebar:
        st.markdown(
            '<div class="vs-brand"><div class="vs-logo"></div>'
            '<div><div class="vs-brand-name">Valuation Suite</div>'
            '<div class="vs-brand-sub">CRR 이항모형</div></div></div>'
            f'{items}'
            f'<div class="vs-status"><span class="vs-dot"></span>'
            f'CRR · 정상 가동</div>',
            unsafe_allow_html=True,
        )


def render_topbar(last_run: str) -> None:
    """상단 바: 브레드크럼 · 검색 · 보고서 내보내기 · 아바타 · 최종 실행 시각."""
    st.markdown(
        '<div class="vs-topbar">'
        '<div class="vs-crumb">가치평가<span class="sep">/</span>파생상품'
        '<span class="sep">/</span><b>이항모형</b></div>'
        '<div class="vs-top-right">'
        '<div class="vs-search">⌕ 계약·종목 검색</div>'
        '<div class="vs-export">보고서 내보내기</div>'
        '<div class="vs-avatar">VS</div>'
        f'<div class="vs-runat">최종 실행<br>{last_run}<br>'
        f'<span style="opacity:.7">build {APP_BUILD}</span></div>'
        '</div></div>',
        unsafe_allow_html=True,
    )


def render_hero(result: dict | None) -> None:
    """히어로 결과카드: 공정가치(주당) 큰 숫자 + 교차검증 대비 + 배지."""
    if not result:
        st.markdown(
            '<div class="vs-hero">'
            '<div class="vs-hero-badge vs-badge-wait">대기 중</div>'
            '<div class="vs-hero-label">옵션 공정가치 (주당)</div>'
            '<div class="vs-hero-value">— <small>원</small></div>'
            '<div class="vs-hero-sub" style="color:rgba(246,244,239,.55)">'
            '좌측에 조건을 입력하고 가치평가 실행을 누르면 결과가 표시됩니다</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        return
    r = result["results"]
    cc = result["cross_check"]
    unit = r["unit_value_krw"]
    if cc.get("skipped"):
        sub = "몬테카를로 교차검증: 생략됨"
    else:
        diff = cc["mc_value"] - unit
        sign = "+" if diff >= 0 else "−"
        sub = (f"몬테카를로 교차검증 대비 {sign}{_won(abs(diff), 2)}원 "
               f"(MC {_won(cc['mc_value'], 0)}원)")
    badge = ('<div class="vs-hero-badge vs-badge-ok">평가 완료 ✓</div>'
             if cc.get("skipped") or cc.get("passed")
             else '<div class="vs-hero-badge vs-badge-wait">교차검증 확인 필요</div>')
    st.markdown(
        f'<div class="vs-hero">{badge}'
        '<div class="vs-hero-label">옵션 공정가치 (주당)</div>'
        f'<div class="vs-hero-value">{_won(unit, 0)} <small>원</small></div>'
        f'<div class="vs-hero-sub">{sub}</div>'
        '</div>',
        unsafe_allow_html=True,
    )


def render_kpis(result: dict) -> None:
    """KPI 스탯 타일 행: 내재가치 · 시간가치 · 총 평가액 · 교차검증."""
    vi = result["valuation_inputs"]
    r = result["results"]
    cc = result["cross_check"]
    s0 = vi["underlying_price_krw"]
    strike = vi["strike_price_krw"]
    unit = r["unit_value_krw"]
    intrinsic = max(s0 - strike, 0.0)           # max(S₀−K, 0) — 단순 표시 산술
    time_value = max(unit - intrinsic, 0.0)     # 공정가치 − 내재가치
    if cc.get("skipped"):
        cc_val, cc_cls, cc_sub = "생략", "", "교차검증 미실행"
    elif cc.get("passed"):
        cc_val, cc_cls, cc_sub = "합격 ✓", "ok", "95% 신뢰구간 내"
    else:
        cc_val, cc_cls, cc_sub = "불합격 ✗", "", "신뢰구간 밖"
    tiles = [
        ("내재가치", f"{_won(intrinsic, 0)} <small style='font-size:14px'>원</small>",
         "max(S₀ − K, 0) · 주당"),
        ("시간가치", f"{_won(time_value, 0)} <small style='font-size:14px'>원</small>",
         "공정가치 − 내재가치"),
        ("총 평가액", f"{_won(r['total_value_krw'] / 1e8, 2)} <small style='font-size:14px'>억원</small>",
         f"{_won(unit, 0)}원 × {r['quantity_shares']:,}주"),
        ("몬테카를로 교차검증", cc_val, cc_sub),
    ]
    cells = "".join(
        f'<div class="vs-tile"><div class="lab">{lab}</div>'
        f'<div class="val {cls if lab.endswith("교차검증") else ""}">{val}</div>'
        f'<div class="sub">{sub}</div></div>'
        for (lab, val, sub), cls in zip(tiles, ["", "", "", cc_cls])
    )
    st.markdown(f'<div class="vs-kpirow">{cells}</div>', unsafe_allow_html=True)


def _crr_params(vi: dict) -> tuple[float, float, float]:
    """결과에 담긴 σ·r·q·Δt로부터 CRR 배수/위험중립확률을 재현(표시용)."""
    import math
    sigma = vi["volatility"]["value"]
    rf = vi["risk_free_rate"]["value"]
    q = vi["dividend_yield"]
    dt = vi["step_years"]
    u = math.exp(sigma * math.sqrt(dt))
    d = 1.0 / u
    growth = math.exp((rf - q) * dt)
    p = (growth - d) / (u - d)
    return u, d, p


def render_var_table(vi: dict) -> None:
    """평가 입력 변수 표 (기호 S₀·K·σ·r·q·T·n·u/d·p 병기)."""
    u, d, p = _crr_params(vi)
    style = ("유럽형 (만기 일괄 행사)" if vi["exercise_style"] == "european"
             else "미국형 (기간 중 행사)")
    rows = [
        ("S₀", "기초자산 가액", f"{_won(vi['underlying_price_krw'], 0)} 원"),
        ("K", "행사가격", f"{_won(vi['strike_price_krw'], 0)} 원"),
        ("K(T)", "만기 행사가격", f"{_won(vi['strike_at_maturity_krw'], 0)} 원"),
        ("σ", "변동성 (연)", f"{vi['volatility']['value'] * 100:.2f} %"),
        ("r", "무위험이자율", f"{vi['risk_free_rate']['value'] * 100:.3f} %"),
        ("q", "배당수익률", f"{vi['dividend_yield'] * 100:.2f} %"),
        ("T", "잔존만기", f"{vi['maturity_years']:.3f} 년"),
        ("n", "트리 스텝 수", f"{vi['binomial_steps']:,}"),
        ("Δt", "스텝 간격", f"{vi['step_years']:.4f} 년"),
        ("u", "상승배수", f"{u:.5f}"),
        ("d", "하락배수", f"{d:.5f}"),
        ("p", "위험중립확률", f"{p:.4f}"),
        ("—", "행사방식", style),
    ]
    body = "".join(
        f'<tr><td class="sym">{sym}</td><td class="lab">{lab}</td>'
        f'<td class="val">{val}</td></tr>'
        for sym, lab, val in rows
    )
    st.markdown(f'<table class="vs-vartable">{body}</table>', unsafe_allow_html=True)


def render_lattice(vi: dict, steps: int = 4) -> None:
    """이항 격자 개념도 (SVG): 실제 u·d 배수로 재결합 트리 구조를 표시.
    ITM(노드가≥K)=오렌지 채움, OTM=흰 배경+외곽선. 실제 스텝 수는 캡션에 명기."""
    u, d, _ = _crr_params(vi)
    s0 = vi["underlying_price_krw"]
    strike = vi["strike_price_krw"]
    W, H, pad = 360, 240, 26
    x_gap = (W - 2 * pad) / steps
    y_gap = (H - 2 * pad) / (2 * steps)
    cx = W / 2
    edges, nodes = [], []
    coords = {}
    for i in range(steps + 1):
        x = pad + i * x_gap
        for j in range(i + 1):                       # j = 상승 횟수
            y = pad + (H - 2 * pad) / 2 + (i - 2 * j) * y_gap
            coords[(i, j)] = (x, y)
    for i in range(steps):
        for j in range(i + 1):
            x0, y0 = coords[(i, j)]
            for nj in (j, j + 1):
                x1, y1 = coords[(i + 1, nj)]
                edges.append(
                    f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" '
                    f'stroke="#EBE7DE" stroke-width="1.4"/>')
    for (i, j), (x, y) in coords.items():
        price = s0 * (u ** j) * (d ** (i - j))
        itm = price >= strike
        fill = "#E8490F" if itm else "#FFFFFF"
        stroke = "#E8490F" if itm else "#C9C2B4"
        txt = "#FFFFFF" if itm else "#8B857A"
        nodes.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="11" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="1.6"/>'
            f'<text x="{x:.1f}" y="{y + 3:.1f}" font-size="7.5" text-anchor="middle" '
            f'fill="{txt}" font-weight="600">{price / 1000:.1f}k</text>')
    svg = (f'<div class="vs-lattice-wrap"><svg viewBox="0 0 {W} {H}" width="100%" '
           f'style="max-width:{W}px">{"".join(edges)}{"".join(nodes)}</svg></div>'
           '<div class="vs-legend">'
           '<span><span class="vs-lg-fill"></span>ITM (노드가 ≥ K)</span>'
           '<span><span class="vs-lg-out"></span>OTM (노드가 &lt; K)</span></div>'
           f'<div class="vs-note" style="margin-top:6px">개념도(4스텝) — '
           f'실제 평가는 n = {vi["binomial_steps"]:,} 스텝 재결합 트리로 계산됩니다.</div>')
    st.markdown(svg, unsafe_allow_html=True)


def render_param_chips(vi: dict) -> None:
    """모형 파라미터 칩 (Greeks 칩 컴포넌트 스타일 재사용).
    Greeks는 엔진이 산출하지 않으므로, 실제 CRR 구동 파라미터를 칩으로 표시(허구 금지)."""
    u, d, p = _crr_params(vi)
    chips = [
        ("σ", "변동성 (연)", f"{vi['volatility']['value'] * 100:.2f}%"),
        ("r", "무위험이자율", f"{vi['risk_free_rate']['value'] * 100:.3f}%"),
        ("q", "배당수익률", f"{vi['dividend_yield'] * 100:.2f}%"),
        ("p", "위험중립확률", f"{p:.4f}"),
        ("u", "상승배수", f"{u:.4f}"),
        ("d", "하락배수", f"{d:.4f}"),
    ]
    cells = "".join(
        f'<div class="vs-chip"><div class="g">{g}</div>'
        f'<div><div class="g-name">{name}</div><div class="g-val">{val}</div></div></div>'
        for g, name, val in chips
    )
    st.markdown(f'<div class="vs-chips">{cells}</div>', unsafe_allow_html=True)


# ── 네비 레일 + 상단 바 렌더 ──
_last_run = "—"
if "result" in st.session_state:
    _last_run = st.session_state["result"].get("meta", {}).get("run_at", "—")
render_sidebar()
render_topbar(_last_run)

# ── 히어로·KPI 슬롯 (결과 계산 후 채운다) ──
hero_slot = st.container()
kpi_slot = st.container()

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
        # 기본값: 첨부 JSON이 있으면 그것, 없으면 샘플 계약(보유자 예시 포함)을 채운다
        prefill = {}
        if uploaded is not None:
            try:
                prefill = json.loads(uploaded.read().decode("utf-8-sig"))
                st.success(f"계약정보 로드: {prefill.get('contract', {}).get('contract_name', '(이름 없음)')}")
            except Exception as exc:
                st.error(f"JSON 파싱 실패: {exc}")
        else:
            sample = ROOT / "data" / "sample_contract.json"
            if sample.exists():
                prefill = json.loads(sample.read_text(encoding="utf-8-sig"))

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

        # 상장이면 기초자산 종목코드를 받아 자기 주가로 변동성을 산출한다 (피어그룹 불필요)
        underlying_ticker = ""
        if listing_status == "상장":
            underlying_ticker = st.text_input(
                "기초자산 종목코드 (6자리)", str(pu.get("ticker", "") or ""),
                help="상장주식은 이 종목의 주가로 변동성을 직접 산출합니다 — 피어그룹이 필요 없습니다.")

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
        st.caption("계약서상 행사범위·옵션 대가(보장수익률) 및 보유자별 행사비율. "
                   "콜옵션 대상 = 대상주식수량 × 행사범위, 보유자별 수량 = 대상 × 행사비율")

        t1, t2 = st.columns(2)
        with t1:
            exercise_scope = st.number_input(
                "행사범위 (%)", 0.01, 100.0,
                float(pt.get("exercise_scope", 1.0)) * 100, 1.0,
                help="대상주식 중 콜옵션 행사 대상이 되는 비율 (예: 35%)")
        with t2:
            strike_growth = st.number_input(
                "옵션 대가율 (연 %, 0=고정)", 0.0, 50.0,
                float(pt.get("strike_growth_rate", 0.0)) * 100, 0.5,
                help="행사 시점까지 보장하는 연 수익률. 행사가격이 K(t) = 기준가 × (1+대가율)^t 로 "
                     "복리 상승합니다. 0이면 만기까지 고정 행사가격.")

        st.markdown("**옵션 보유자별 행사비율** — 여러 명이면 행을 추가하세요")
        default_holders = pt.get("holders")
        if not default_holders:
            _alloc = pt.get("allocation_ratio", 1.0)
            default_holders = [{"name": "평가대상 보유자", "ratio": _alloc}]
        holders_df = pd.DataFrame([
            {"보유자": h.get("name", ""), "행사비율(%)": float(h["ratio"]) * 100}
            for h in default_holders
        ])
        holders_df = st.data_editor(
            holders_df, num_rows="dynamic", use_container_width=True,
            column_config={
                "보유자": st.column_config.TextColumn(width="large"),
                "행사비율(%)": st.column_config.NumberColumn(min_value=0.0, max_value=100.0, step=1.0),
            })

        holders = [
            {"name": str(row["보유자"]).strip() or f"보유자{i+1}",
             "ratio": float(row["행사비율(%)"]) / 100.0}
            for i, (_, row) in enumerate(holders_df.iterrows())
            if float(row.get("행사비율(%)") or 0) > 0
        ]
        _scoped = round(quantity * exercise_scope / 100)
        _opt_qty = sum(round(_scoped * h["ratio"]) for h in holders)
        _total_ratio = sum(h["ratio"] for h in holders)
        _years = max((maturity_date - contract_date).days, 0) / 365
        _strike_end = strike * (1 + strike_growth / 100) ** _years
        if _total_ratio > 1 + 1e-9:
            st.warning(f"보유자 행사비율 합계가 {_total_ratio*100:.1f}%로 100%를 초과합니다.")
        st.markdown(
            f"→ 행사 대상 {_scoped:,}주 ({quantity:,}주 × {exercise_scope:g}%) · "
            f"**평가대상 콜옵션 수량 {_opt_qty:,}주** (보유자 {len(holders)}명, 합계 {_total_ratio*100:g}%) · "
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

    # ── 04 변동성 산출 (상장: 자기 주가 / 비상장: 피어그룹) ──
    peers_df = None
    with st.container(border=True):
        st.markdown('### <span class="num">04</span> 변동성 자동 산출', unsafe_allow_html=True)

        if listing_status == "상장":
            st.caption("기초자산이 **상장주식**이므로 위에 입력한 종목코드의 일별 종가로 "
                       "변동성을 직접 산출합니다. 피어그룹은 필요하지 않습니다.")
            cs1, cs2 = st.columns([2, 1])
            with cs1:
                if underlying_ticker.strip():
                    st.info(f"기초자산 **{issuer or underlying_ticker}** ({underlying_ticker}) 주가로 변동성 산출")
                else:
                    st.warning("상단 계약 조건에서 **기초자산 종목코드**를 입력하세요. "
                               "(입력 전까지는 아래 '변동성 직접 입력'을 사용하세요)")
            with cs2:
                lookback = st.number_input("수집 기간 (년)", 0.5, 5.0, 1.0, 0.5)
                manual_vol = st.number_input("변동성 직접 입력 (%, 0=자동)", 0.0, 200.0, 0.0, 1.0,
                                             help="0보다 크게 입력하면 자기 주가 산출 대신 이 값을 사용")
        else:
            st.caption("기초자산이 **비상장주식**이므로 유사 상장기업(대용기업)의 변동성 평균으로 추정합니다. "
                       "**기업명 칸을 클릭하면 상장사 목록에서 검색·선택할 수 있고, 선택하면 종목코드가 자동으로 채워집니다.** "
                       "(종목코드를 직접 입력해도 기업명이 채워집니다)")

            # 세션에 피어 표를 보관하고, 편집 시 KRX 목록으로 빈 칸을 자동 완성한다
            if "peers_df" not in st.session_state:
                st.session_state["peers_df"] = pd.DataFrame(
                    prefill.get("volatility_estimation", {}).get("peer_group")
                    or [
                        {"name": "안랩", "ticker": "053800"},
                        {"name": "더존비즈온", "ticker": "012510"},
                        {"name": "한글과컴퓨터", "ticker": "030520"},
                        {"name": "웹케시", "ticker": "053580"},
                        {"name": "알서포트", "ticker": "131370"},
                    ]
                )
            # data_editor는 같은 key로는 내부 편집 상태(추가·수정 행)를 계속 재적용하므로,
            # 자동완성으로 표를 갱신할 때마다 key를 바꿔 위젯을 새 데이터로 초기화한다
            if "peers_ver" not in st.session_state:
                st.session_state["peers_ver"] = 0

            def _cell(v) -> str:
                """편집 표 셀 값을 문자열로 정규화 (None/NaN → 빈 문자열)."""
                if v is None:
                    return ""
                try:
                    if pd.isna(v):
                        return ""
                except (TypeError, ValueError):
                    pass
                return str(v).strip()

            cp1, cp2 = st.columns([2, 1])
            with cp1:
                prev_df = st.session_state["peers_df"]  # 직전 상태 (편집 방향 판별용)
                edited = st.data_editor(
                    st.session_state["peers_df"], num_rows="dynamic", use_container_width=True,
                    column_config={
                        # 기업명: 상장사 목록에서 검색·선택 (타이핑하면 후보가 뜬다)
                        "name": st.column_config.SelectboxColumn(
                            "기업명", options=krx_lookup.all_names(), required=False,
                            help="클릭 후 타이핑하면 상장사 후보가 검색됩니다"),
                        "ticker": st.column_config.TextColumn("종목코드", help="6자리, 직접 입력하면 기업명이 자동 조회됩니다"),
                    },
                    key=f"peers_editor_{st.session_state['peers_ver']}")

                # 방금 편집된 칸을 기준으로 반대편을 자동완성한다 (지운 칸은 되채우지 않음)
                def _prev_at(i: int) -> tuple[str, str]:
                    if i < len(prev_df):
                        r = prev_df.iloc[i]
                        return _cell(r.get("name")), _cell(r.get("ticker"))
                    return "", ""  # 새로 추가된 행

                filled_rows = []
                for i in range(len(edited)):
                    row = edited.iloc[i]
                    nm_raw, tk_raw = _cell(row.get("name")), _cell(row.get("ticker"))
                    pv_nm, pv_tk = _prev_at(i)
                    nm, tk = krx_lookup.autofill_directed(
                        nm_raw, tk_raw,
                        name_changed=(nm_raw != pv_nm),
                        ticker_changed=(tk_raw != pv_tk))
                    filled_rows.append({"name": nm, "ticker": tk})
                filled = pd.DataFrame(filled_rows or [{"name": "", "ticker": ""}])
                prev_normalized = pd.DataFrame(
                    [{"name": _cell(r.get("name")), "ticker": _cell(r.get("ticker"))}
                     for _, r in prev_df.iterrows()] or [{"name": "", "ticker": ""}])

                def _for_widget(df: pd.DataFrame) -> pd.DataFrame:
                    # 드롭다운(Selectbox) 칸의 빈 값은 ""가 아닌 None이어야 한다
                    out = df.copy()
                    out["name"] = out["name"].map(lambda v: v if v else None)
                    return out

                # 편집·삭제·추가·자동완성 등 어떤 변화든 즉시 세션에 흡수하고
                # 위젯을 재초기화(key 변경)한다 — 삭제한 행이 부활하거나
                # 편집 내역이 이중 적용되는 문제를 원천 차단
                if not filled.reset_index(drop=True).equals(prev_normalized.reset_index(drop=True)):
                    st.session_state["peers_df"] = _for_widget(filled)
                    st.session_state["peers_ver"] += 1
                    st.rerun()
                peers_df = filled
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
            # 직접 입력 금리는 수익률 곡선이 없어 기간구조 할인이 불가하다.
            # 잘못된 조합(직접입력+기간구조)이 성립하지 못하도록 UI에서 spot으로 고정한다.
            if rf_mode == "manual":
                st.selectbox(
                    "할인 방식", ["단일 spot rate (직접 입력 금리는 이 방식만 가능)"],
                    disabled=True,
                    help="직접 입력한 단일 금리는 기간구조(스텝별 선도이자율) 할인을 쓸 수 없습니다. "
                         "기간구조 할인을 쓰려면 무위험이자율을 '자동'으로 두세요.")
                discounting = "spot"
            else:
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
    # ── 실행 전 입력 사전 검증: 엔진에 도달하기 전 잘못된 조합을 명확히 차단한다 ──
    #   (오도성 메시지·raw 예외로 표면화되기 전에 사용자 언어로 안내)
    preflight_errors = []
    # F3: 상장인데 종목코드가 없고 변동성 자동이면 → 자기 주가 산출 불가
    if listing_status == "상장" and not underlying_ticker.strip() and manual_vol == 0.0:
        preflight_errors.append(
            "상장 기초자산은 **종목코드(6자리)** 가 필요합니다. "
            "상단 계약 조건에서 종목코드를 입력하거나, 변동성을 직접 입력(%>0)하세요."
        )
    # F4: 보유자 행사비율 합계 > 100%면 실행 자체를 차단 (엔진 도달 전)
    if _total_ratio > 1 + 1e-9:
        preflight_errors.append(
            f"보유자 행사비율 합계가 {_total_ratio*100:.1f}%로 100%를 초과합니다. "
            "행사비율을 조정하세요."
        )

if run_clicked and preflight_errors:
    with right:
        for _msg in preflight_errors:
            st.error(_msg)

if run_clicked and not preflight_errors:
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
            "ticker": underlying_ticker.strip().zfill(6) if underlying_ticker.strip() else "",
        },
        "option_terms": {
            "option_type": "call",
            "exercise_style": exercise_style,
            "quantity_shares": int(quantity),
            "strike_price_krw": float(strike),
            "exercise_scope": exercise_scope / 100.0,
            "holders": holders,
            "strike_growth_rate": strike_growth / 100.0,
            "closing_date": maturity_date.isoformat(),
            "settlement": settlement,
        },
    }
    # 비상장일 때만 피어그룹을 사용한다 (상장은 자기 주가로 산출)
    peer_group = [
        {"name": str(r["name"]).strip(), "ticker": str(r["ticker"]).strip().zfill(6)}
        for _, r in peers_df.iterrows()
        if str(r.get("ticker", "")).strip()
    ] if peers_df is not None else []
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

# ════════════════════════════ 우측: 결과 분석 패널 ════════════════════════════
with right:
    with st.container(border=True):
        st.markdown('### <span class="num">06</span> 결과 분석', unsafe_allow_html=True)

        if "result" not in st.session_state:
            st.info("좌측에 조건을 입력하고 **가치평가 실행**을 누르면 결과와 보고서 미리보기가 여기에 표시됩니다.")
        else:
            result = st.session_state["result"]
            contract = st.session_state["contract"]
            vi = result["valuation_inputs"]
            r = result["results"]
            cc = result["cross_check"]

            # ── 평가 입력 변수 표 (S₀·K·σ·r·q·T·n·u/d·p) ──
            st.markdown('<div class="vs-section">평가 입력 변수</div>', unsafe_allow_html=True)
            render_var_table(vi)

            # ── 이항 격자 (Binomial Lattice) ──
            st.markdown('<div class="vs-section" style="margin-top:16px">이항 격자 (Binomial Lattice)</div>',
                        unsafe_allow_html=True)
            render_lattice(vi)

            # ── 모형 파라미터 칩 ──
            st.markdown('<div class="vs-section" style="margin-top:16px">모형 파라미터 (CRR)</div>',
                        unsafe_allow_html=True)
            render_param_chips(vi)

            st.markdown('<div class="vs-section" style="margin-top:16px">상세 · 보고서</div>',
                        unsafe_allow_html=True)
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
                    st.session_state.pop("report_html", None)
                    try:
                        with st.spinner("PDF 변환 중..."):
                            pdf_path = report_module.generate_report(contract_path, result_path, out_dir)
                        st.session_state["pdf"] = (pdf_path.name, pdf_path.read_bytes())
                    except Exception as exc:
                        # PDF 변환 실패(배포 환경 chromium 부재 등) → HTML 보고서로 폴백
                        #   조용한 실패 방지: 다운로드 가능한 HTML 산출물을 제공한다
                        try:
                            html_path = report_module.generate_report(
                                contract_path, result_path, out_dir, html_only=True)
                            st.session_state["report_html"] = (
                                html_path.name, html_path.read_bytes())
                            st.warning(
                                f"⚠ PDF 변환에 실패해 HTML 보고서로 대체했습니다({exc}). "
                                "아래에서 HTML을 내려받아 브라우저로 열거나 인쇄(PDF 저장)하세요.")
                        except Exception as exc2:
                            st.error(f"보고서 생성 실패: {exc2}")
                if "pdf" in st.session_state:
                    name, data = st.session_state["pdf"]
                    st.download_button("PDF 다운로드", data, file_name=name, mime="application/pdf",
                                       type="primary", use_container_width=True)
                if "report_html" in st.session_state:
                    name, data = st.session_state["report_html"]
                    st.download_button("HTML 보고서 다운로드 (PDF 폴백)", data, file_name=name,
                                       mime="text/html", type="primary", use_container_width=True)

# ══ 상단 히어로·KPI 슬롯 채우기 (본문 계산 이후 — 최신 세션 결과 반영) ══
#   컬럼보다 먼저 생성한 컨테이너에 나중에 렌더해 시각적 위계(히어로→KPI→본문)를 만든다.
with hero_slot:
    render_hero(st.session_state.get("result"))
if "result" in st.session_state:
    with kpi_slot:
        render_kpis(st.session_state["result"])
