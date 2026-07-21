---
name: reproduce-and-verify
description: 이항모형 가치평가 웹앱의 실패를 라이브(Streamlit Cloud)·로컬 양쪽에서 재현하고, app.py가 한 줄로만 보여주는 "평가 실패: {exc}" 뒤의 진짜 traceback을 캡처하며, 수정 후 결과를 재검증하는 방법. 실패 재현·에러 캡처·라이브/로컬 대조·수정 검증이 필요할 때 반드시 사용. empirical-tester 전용.
---

# 재현·에러 캡처·검증

추측 대신 **실제 관찰**을 만든다. 모든 진단은 여기서 잡은 진짜 에러에서 출발한다.

## 왜 이 절차인가
앱은 `run_valuation.run`의 예외를 `app.py:457`에서 `st.error(f"평가 실패: {exc}")` 한 줄로만 노출한다. 이 한 줄엔 예외 메시지는 있어도 **전체 traceback과 실패 계층**이 없다. 그래서 (1) 라이브에서 증상을 캡처하고 (2) 로컬에서 full traceback을 뽑아 계층을 특정한다.

## A. 라이브 재현 (Streamlit Cloud)
1. 브라우저로 https://binomial-valuation-engine.streamlit.app/ 열기(잠들어 있으면 깨어날 때까지 대기, 최대 2회 새로고침).
2. 기본 샘플값 그대로(또는 지정 입력) "가치평가 실행" 클릭. 계산은 수십 초 걸릴 수 있으니 대기 후 결과 패널 확인.
3. 결과 패널 상단의 빨간 `평가 실패: ...` 문구를 **원문 그대로** 캡처. 정상이면 결과 카드(1주당 공정가치·교차검증)와 "금리·선도" 탭의 폴백 표기 여부를 캡처.
4. iframe 스크롤이 안 먹으면 페이지에 포커스(중립 영역 클릭) 후 `End`/`Home` 키 또는 스크롤. 2~3회 실패 시 중단·보고.

## B. 로컬 full traceback (권장 근거)
번들 스크립트를 쓴다 — 데이터 소스 개별 점검 + 앱 기본값과 동일 조건의 전체 파이프라인을 돌리고, 실패 시 full traceback을 찍는다:
```
python .claude/skills/reproduce-and-verify/scripts/diag_valuation.py
```
출력: Python/패키지 버전 → `[SEIBRO]`/`[FDR]` 도달성 → `[평가]` 성공(수치) 또는 실패(traceback). 이 traceback의 최상단 프레임이 실패 계층을 가리킨다.

## C. 로컬 vs 라이브 대조 (계층 1차 분류)
같은 입력을 로컬·라이브에서 돌린다:
- **둘 다 실패** → 입력검증/계산(logic) 가능성. 로컬 traceback으로 확정.
- **로컬 성공·라이브 실패** → 배포 환경(datasource 네트워크 차단 또는 platform 설정) 강한 신호.
- 에러 지문: `<urlopen error timed out>`=SEIBRO(urllib), `Read timed out`/`HTTPSConnectionPool`=FinanceDataReader(requests), `ValueError`=입력검증, `NotImplementedError`=미지원(콜 외), chromium/`subprocess`=보고서.

## D. 수정 검증 (fixer 이후)
1. 실패하던 **바로 그 시나리오**를 다시 돌린다(로컬 diag + 라이브 클릭).
2. 판정 기준: (a) 정상 결과가 나오거나, (b) 폴백이 동작하되 결과·"금리·선도" 탭·보고서에 `⚠ ... 폴백` 표기가 보이거나, (c) 못 고치는 환경 한계면 사용자 행동을 담은 명확한 에러가 나온다.
3. 정상 경로 회귀 확인: 원래 잘 되던 케이스의 수치가 그대로인지 대조.
4. 결과를 `_workspace/05_empirical_verify.md`에 수정 전/후 비교로 남긴다.

## 산출물
- `_workspace/01_empirical_repro.md`: 재현 절차·캡처 에러 원문·로컬/라이브 결과·1차 계층 추정.
- `_workspace/05_empirical_verify.md`: 수정 전/후 결과·투명 표기 확인.

## 주의
- 화면 문구는 각색 없이 원문 인용. 브라우저 무한 재시도 금지(2~3회 실패 시 로컬로 전환하고 명시).
- 데이터 소스가 그 순간 회복돼 재현이 안 되면 "현재 정상 + 간헐 실패 가능"으로 보고(거짓 음성 방지).
