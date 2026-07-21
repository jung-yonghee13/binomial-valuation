---
name: dashboard-design
description: Streamlit 대시보드(app.py)를 "Valuation Suite" 디자인 시스템(다크 네비 레일 + 크림 배경 + 오렌지 포인트, 다크 히어로 결과카드, KPI 스탯 타일, 이항 격자 시각화, Greeks 칩, 보고서 미리보기 카드)으로 구축·조정하는 방법. dashboard-designer가 UI 작업 시 사용. 웹 디자인·레이아웃 변경·대시보드 개선·"이 시안처럼 바꿔줘"·스타일/색/카드/사이드바 조정 요청 시 반드시 사용.
---

# 대시보드 디자인 시스템 — Valuation Suite

Streamlit 앱을 금융 평가 제품 수준의 완성도로 만든다. **기능(값·계산)은 그대로, 보이는 층만** 바꾼다.

## 핵심 원칙 (Why)
- **토큰 단일 출처**: 색·간격·라운드·폰트는 하나의 `<style>` 블록에 CSS 변수로 정의하고 그것만 참조한다. 값이 곳곳에 흩어지면 유지보수가 무너진다. 토큰 정의는 `references/design-system.md`.
- **기능 불변**: `run_valuation.run` 호출, 위젯이 만드는 값·키는 건드리지 않는다. UI는 표현이지 값의 원천이 아니다.
- **Streamlit스럽게 재현**: 순정 Streamlit은 레이아웃 자유도가 낮다. 시안을 픽셀 복제하려 무리한 해킹을 하지 말고, 위계·색·여백으로 "같은 느낌"을 안정적으로 만든다.
- **접근성**: 대비 WCAG AA, 오렌지 배경 위 텍스트 대비 확인, 색만으로 정보 전달 금지(라벨 병기), 반응형(좁은 화면에서 가로 스크롤 금지).
- **참조 흡수, 베끼기 금지**: 시안의 구조·위계를 이해해 자체 토큰·컴포넌트로 재설계한다. 산출물에 출처 표기·워터마크를 넣지 않는다.

## 레이아웃 구조 (위→아래, 좌→우)
1. **좌측 네비 레일**(다크): 브랜드 로고+명, 메뉴(평가·대시보드·평가모형·시나리오·리포트·데이터), 하단 상태 pill("CRR · 정상 가동"). → Streamlit `sidebar`를 다크로 스타일.
2. **상단 바**: 브레드크럼(가치평가 / 파생상품 / 이항모형), 검색, "보고서 내보내기" 오렌지 버튼, 사용자 아바타, 최종 실행 시각.
3. **히어로 결과카드**(다크+오렌지 글로우): 옵션 공정가치(주당) 큰 숫자 + "Black-Scholes 대비 ±N원".
4. **KPI 스탯 타일 행**: 델타 / 내재가치 / 시간가치 등 3~4개.
5. **2단 본문**: 좌 = 평가 입력 변수 표(S₀·K·σ·r·q·T·n·u/d·p), 우 = 이항 격자(Binomial Lattice) + 수렴 분석 + Greeks 칩.
6. **보고서 미리보기 카드** + "전체 보고서 열기".

## Streamlit 구현 기법
- `st.set_page_config(layout="wide")` + 기본 크롬 숨김: `.streamlit/config.toml`의 `toolbarMode="minimal"`, CSS로 메뉴/푸터/deploy 버튼 `display:none`.
- 카드/히어로/스탯 타일: `st.markdown("<div class='...'>...</div>", unsafe_allow_html=True)` + `<style>` 블록. 반복 마크업은 파이썬 헬퍼 함수(`stat_tile(label, value, sub)`)로.
- 레이아웃: `st.columns([...])`(비율)·`st.container`. 사이드바 다크: `[data-testid="stSidebar"]` 셀렉터.
- 숫자: 큰 KPI는 `font-variant-numeric: tabular-nums`, 굵게. 라벨은 작게·회색·대문자 letter-spacing.
- 격자/수렴 차트: 기존 계산 결과(JSON)를 입력으로, matplotlib 또는 인라인 SVG로 렌더. 색은 토큰(오렌지=ITM/채움, 회색 외곽선=OTM).

## 절차
1. 현재 `app.py` UI·인라인 CSS·`.streamlit/config.toml` 읽기.
2. 컴포넌트 단위로 적용(네비 → 상단바 → 히어로 → 스탯 → 본문 → 보고서 카드). 한 번에 하나씩.
3. **로컬 렌더 검증**: `streamlit run app.py`를 헤드리스로 띄우고 브라우저로 실제 화면 스크린샷 확인("코드상 맞음"이 아니라 "화면에서 맞음"). 반응형·대비 점검.
4. empirical-tester에 기능 회귀 검증 요청(디자인 변경이 위젯/세션을 안 깼는지).

## 산출물
`_workspace/04_design.md`: 적용 컴포넌트, 사용 토큰, 렌더 스크린샷 경로, Streamlit 한계로 남긴 트레이드오프.

## 하지 말 것
- 계산/데이터 로직 수정. 토큰 밖 임의 색·간격 하드코딩 산발. 깨지기 쉬운 과도한 DOM 해킹. 픽셀 복제를 위한 기능 훼손.
