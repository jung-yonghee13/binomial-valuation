# Valuation Suite — 디자인 토큰 & 컴포넌트 스펙

참조 시안(Valura 대시보드)의 위계를 흡수해 재설계한 **자체 디자인 시스템**. 아래 토큰만 사용한다.

## 1. 색 토큰 (CSS 변수)
```css
:root{
  /* 배경/표면 */
  --bg:        #F6F4EF;   /* 크림 오프화이트 (앱 배경) */
  --surface:   #FFFFFF;   /* 카드 */
  --ink:       #17150F;   /* 다크 (네비 레일·히어로 카드 배경) */
  --ink-soft:  #262117;   /* 다크 표면 위 살짝 밝은 층 */
  /* 텍스트 */
  --text:      #1E1B16;   /* 본문 */
  --text-mut:  #8B857A;   /* 라벨·보조 (대비 확인) */
  --text-inv:  #F6F4EF;   /* 다크 위 텍스트 */
  /* 포인트 */
  --accent:    #E8490F;   /* 오렌지 (주 포인트·버튼·채운 노드) */
  --accent-2:  #F2A03D;   /* 앰버 (글로우·강조 수치) */
  --success:   #3BA55D;   /* "평가 완료" 배지·정상 상태 */
  /* 선/그림자 */
  --line:      #EBE7DE;   /* 헤어라인 보더 */
  --node-out:  #C9C2B4;   /* 격자 OTM 외곽선 노드 */
  --shadow:    0 1px 2px rgba(23,21,15,.04), 0 8px 24px rgba(23,21,15,.06);
  --glow:      0 0 0 1px rgba(232,73,15,.15), 0 12px 40px rgba(232,73,15,.18);
  /* 형태 */
  --r-card: 16px;  --r-tile: 12px;  --r-pill: 999px;
  --pad-card: 20px;  --gap: 16px;
}
```
다크(네비/히어로) 위에서는 `--text-inv`를 본문색으로, 라벨은 `rgba(246,244,239,.55)` 정도로.

## 2. 타이포
- 폰트: 시스템 산세리프 우선(가독성). 한글 포함되므로 Pretendard/Noto Sans KR가 있으면 사용, 없으면 `-apple-system, "Segoe UI", Roboto, sans-serif`.
- 위계:
  - 히어로 공정가치: 40~48px, 700, `tabular-nums`.
  - KPI 값: 24~28px, 700, `tabular-nums`.
  - 섹션 제목: 15px, 600.
  - 라벨/캡션: 12px, 500, `--text-mut`, `letter-spacing:.02em`(대문자 라벨은 `.06em`).
- 모든 금액·수치는 `font-variant-numeric: tabular-nums`(자릿수 정렬).

## 3. 컴포넌트 스펙
### 네비 레일 (다크 사이드바)
- 배경 `--ink`, 폭 고정(~220px). 상단 브랜드(로고 마름모 + 이름 + 작은 대문자 부제).
- 메뉴 아이템: 아이콘 + 라벨, 활성 항목은 왼쪽 오렌지 바(3px) + `--ink-soft` 배경 + `--accent` 텍스트.
- 하단 상태 pill: 초록 점 + "CRR v… · 정상 가동", `--r-pill`, 어두운 표면.

### 상단 바
- 좌: 브레드크럼(`--text-mut`, `/` 구분). 우: 검색 인풋(둥근, 헤어라인), 오렌지 "보고서 내보내기" 버튼, 아바타(이니셜 원), 최종 실행 시각(작게).

### 히어로 결과카드 (다크 + 글로우)
- 배경 `--ink`, `--r-card`, `box-shadow: --glow`, 오렌지 방사형 글로우(좌상단 `radial-gradient`).
- 제목(라벨) "옵션 공정가치 (주당)" → 큰 숫자(`--text-inv`) → 보조("Black-Scholes 대비 +N원", `--accent-2`).
- 우상단 "평가 완료" 배지(`--success` 배경 옅게 + 초록 텍스트).

### KPI 스탯 타일
- `--surface`, `--r-tile`, `--shadow`, `--pad-card`. 라벨(작게·회색) → 값(크게·굵게) → 보조 캡션.
- 헬퍼: `stat_tile(label, value, sub=None)` → 마크업 반환.

### 입력 변수 표
- 헤어라인으로 구분된 라벨↔값 2열. 라벨 `--text-mut`, 값 오른쪽 정렬 `tabular-nums`. 기호(S₀·K·σ·r·q·T·n·u/d·p) 병기.

### 이항 격자 (Binomial Lattice)
- 노드: ITM/채움 = `--accent` 원, OTM = 흰 배경 + `--node-out` 외곽선. 엣지 = `--line`. 노드 옆 값(작게).
- ITM/OTM 토글은 표시 필터. 계산값(트리 JSON)에서 렌더(matplotlib/SVG).

### 수렴 분석 차트
- 스텝 증가에 따른 값이 BS로 수렴하는 진동 곡선. 선 `--accent`, 기준선 점선 `--text-mut`.

### Greeks 칩
- 각 그릭(Δ Γ ν Θ ρ): 아이콘 칩(옅은 오렌지 배경) + 이름/설명 + 값. 세로 나열 또는 2열 그리드.

### 보고서 미리보기 카드
- 문서 썸네일(비율 유지) + "전체 보고서 열기" 버튼(헤어라인, 보조).

## 4. Streamlit 주입 스니펫 (패턴)
```python
st.markdown("""<style>
:root{ /* ...위 토큰... */ }
.stApp{ background:var(--bg); }
[data-testid="stSidebar"]{ background:var(--ink); }
[data-testid="stSidebar"] *{ color:var(--text-inv); }
#MainMenu, footer, [data-testid="stToolbar"]{ display:none; }
.vs-hero{ background:var(--ink); color:var(--text-inv); border-radius:var(--r-card);
  padding:24px; box-shadow:var(--glow);
  background-image:radial-gradient(120% 80% at 0% 0%, rgba(242,160,61,.18), transparent 60%); }
.vs-tile{ background:var(--surface); border-radius:var(--r-tile); padding:var(--pad-card);
  box-shadow:var(--shadow); }
.vs-label{ color:var(--text-mut); font-size:12px; letter-spacing:.02em; }
.vs-num{ font-variant-numeric:tabular-nums; font-weight:700; }
.vs-badge{ background:rgba(59,165,93,.12); color:var(--success);
  border-radius:var(--r-pill); padding:2px 10px; font-size:12px; }
</style>""", unsafe_allow_html=True)

def stat_tile(label, value, sub=""):
    sub_html = f"<div class='vs-label'>{sub}</div>" if sub else ""
    return (f"<div class='vs-tile'><div class='vs-label'>{label}</div>"
            f"<div class='vs-num' style='font-size:26px'>{value}</div>{sub_html}</div>")
```

## 5. 검증 기준
- 라이트/다크 뷰어 모두에서 대비 확보(다크 사이드바는 항상 어둡게 고정).
- 좁은 화면에서 본문 가로 스크롤 없음(격자·표는 자체 컨테이너 `overflow-x:auto`).
- 오렌지 버튼 위 흰 텍스트 대비 AA. 색만으로 ITM/OTM 구분하지 말고 라벨/외곽선 병기.
