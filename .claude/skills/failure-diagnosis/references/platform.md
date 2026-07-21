# 플랫폼·배포·보고서 계층 진단 참조

담당: platform-diagnostician. 대상: `app.py`(Streamlit), `.streamlit/config.toml`, `requirements.txt`, `packages.txt`, `valuation/report.py`(PDF).

## 세 갈래
### 1) Streamlit 실행 계층
- 세션 상태(`st.session_state["result"]/["contract"]`), 위젯 기본값, 버튼→rerun→run_clicked 흐름.
- 증상: 버튼을 눌러도 결과 패널이 안내문 그대로 → 클릭이 run_clicked로 안 이어짐(포커스/렌더 타이밍) 또는 예외로 세션에 결과 미저장.
- `app.py:449~457`의 try/except가 예외를 `평가 실패: {exc}`로 표시. `보고서 생성 실패: {exc}`는 별개(PDF 단계).
- 위젯이 만든 dict ↔ 엔진 키 경계면은 logic 참조와 함께 본다.

### 2) 배포 환경 차이 (로컬 vs Streamlit Cloud)
- `requirements.txt`(파이썬 의존성)·`packages.txt`(apt: `chromium`, `fonts-nanum`)·`.streamlit/config.toml` 점검.
- 흔한 원인: 로컬엔 있으나 클라우드에 없는 의존성, 한글 폰트 누락(깨짐), 부팅 지연/슬립(keepalive 워크플로 있음), 재배포 미반영(`APP_BUILD` 버전으로 판별 — push 후 값이 안 바뀌면 재배포 지연).
- 배포 서버는 직접 접속 불가 → 코드·설정 + empirical-tester의 라이브 관찰로 추론.

### 3) 보고서/PDF 계층 (`report.py`)
- `html_to_pdf`: 브라우저 실행 파일 탐색 — 로컬은 `C:\Program Files\...\chrome.exe`, 리눅스는 PATH의 `chromium`/`google-chrome`/`msedge`. `packages.txt`에 `chromium` 없으면 클라우드에서 실패.
- `--no-sandbox`(컨테이너 필수), `--print-to-pdf`, timeout(120s), `subprocess.run(check=True)`.
- 증상: 평가는 되는데 "보고서 생성 실패" → PDF 계층. chromium 미탐색/타임아웃/폰트.

## 로컬↔클라우드 대조
platform 문제의 핵심 질문: "코드가 아니라 **환경 설정**이 원인인가?" 로컬 성공+클라우드 실패이고 네트워크(datasource)가 아니면 여기.

## 권고 방향 (fixer에게)
- 배포 설정 누락: `requirements.txt`/`packages.txt`/`config.toml` 보정.
- 재배포 미반영: `APP_BUILD` 갱신 커밋으로 강제 재배포 판별, push 후 확인.
- PDF 실패: 실행 파일 탐색 견고화 + 실패 시 HTML 폴백/명확한 안내(조용한 실패 금지).
- Streamlit 흐름 결함: 세션/rerun 로직 수정. UI 표현 문제면 dashboard-designer와 협업.
