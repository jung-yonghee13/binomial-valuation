---
name: valuation-app-doctor
description: 이항모형 가치평가 웹앱(binomial-valuation, Streamlit Cloud)의 에러·가치평가 실패를 여러 계층에서 진단하고 근본 수정한 뒤 검증·배포·문서화까지 잇는 에이전트 팀 오케스트레이터. 그리고 대시보드 UI/레이아웃을 Valuation Suite 디자인으로 구축·조정한다. "평가 실패", "에러 나", "웹앱 안 돼", "가치평가가 안 됨", "디자인 바꿔줘", "레이아웃 조정", 그리고 후속으로 "다시 진단", "재실행", "이 부분만 다시", "수정 보완", "이전 결과 기반으로" 요청 시 이 스킬을 사용. 단순 개념 질문은 직접 응답.
---

# valuation-app-doctor — 진단·수정·디자인 에이전트 팀 오케스트레이터

이항모형 가치평가 웹앱의 문제를 **재현→계층별 진단(팬아웃)→근본 수정→검증→배포·문서**로 잇는 파이프라인, 그리고 대시보드 **디자인** 트랙을 조율한다.

**실행 모드: 에이전트 팀** (`TeamCreate` + `SendMessage` + `TaskCreate`). 팀 도구는 harness 플러그인 소속이므로 `/reload-plugins` 후 사용 가능. 도구가 없으면 서브 에이전트(`Agent`, `model: "opus"`)로 대체 실행한다.

## Phase 0: 컨텍스트 확인
1. `_workspace/` 존재 여부로 실행 모드 판별:
   - 없음 → **초기 실행**(전체 파이프라인).
   - 있음 + 부분 수정 요청 → **부분 재실행**(해당 에이전트만 재호출).
   - 있음 + 새 문제 → **새 실행**(`_workspace/`를 `_workspace_prev/`로 이동 후 재시작).
2. 요청 성격 분기:
   - **문제 해결 트랙**(에러/실패) → Phase 1~4 전체.
   - **디자인 트랙**(레이아웃/스타일) → dashboard-designer 중심(Phase 1의 진단 팬아웃 생략, 2·3·4는 UI 회귀 관점으로).

## Phase 1: 재현 & 진단 (팬아웃)
1. `empirical-tester`가 라이브·로컬에서 재현하고 진짜 에러/traceback을 캡처 → `_workspace/01_empirical_repro.md`.
2. 캡처를 셋에 공유하고 **병렬 진단**:
   - `datasource-diagnostician` → `_workspace/02_diag_datasource.md`
   - `logic-diagnostician` → `_workspace/02_diag_logic.md`
   - `platform-diagnostician` → `_workspace/02_diag_platform.md`
3. 셋은 `SendMessage`로 결론을 교차 검토. 상충 시 empirical-tester의 실제 관찰이 최종 기준.

## Phase 2: 수정
`root-cause-fixer`가 3개 진단을 종합해 근본 수정 + 로컬 스모크 테스트(정상/실패 경로) → `_workspace/03_fix.md`.
(디자인 트랙이면 `dashboard-designer`가 `_workspace/04_design.md`로 대체 수행.)

## Phase 3: 검증
`empirical-tester`가 실패하던 시나리오를 라이브·로컬에서 재실행해 (정상 / 투명 폴백 / 명확한 에러) 판정 + 정상 경로 회귀 확인 → `_workspace/05_empirical_verify.md`. 실패 시 Phase 2로 되돌림(1회 재시도).

## Phase 4: 배포 & 문서 (사용자 승인)
`release-manager`가 커밋 → (승인 후)push·재배포 확인 → (승인 후)Notion 업데이트 로그·설명 갱신 → `_workspace/06_release.md`. 최종 요약 보고.

## 팀 구성 (TeamCreate)
리더(오케스트레이터) + `empirical-tester`, `datasource-diagnostician`, `logic-diagnostician`, `platform-diagnostician`, `root-cause-fixer`, `release-manager`, `dashboard-designer`. 모든 Agent 호출에 `model: "opus"`.
- 문제 트랙: 진단 3인 + empirical + fixer + release (6인 활성).
- 디자인 트랙: dashboard-designer + empirical(회귀) + release (3인 활성).

## 데이터 전달
- **태스크 기반**(`TaskCreate`/의존): repro → diag(3, 병렬) → fix → verify → release.
- **파일 기반**(`_workspace/{phase}_{agent}_{artifact}.md`): 중간 산출물·감사 추적. `_workspace/`는 보존.
- **메시지 기반**(`SendMessage`): 진단 교차검토·검증 회신 등 실시간 조율.

## 에러 핸들링
- 에이전트 1회 재시도 후 재실패 시 그 결과 없이 진행하고 최종 보고에 누락 명시.
- 진단 상충은 삭제하지 말고 병기 → empirical 관찰로 판정.
- 라이브 재현 불가(소스 일시 회복)면 "현재 정상+간헐 실패 가능"으로 보고(거짓 음성 방지).
- push/Notion 등 외부 반영은 **사용자 승인 없이는 실행하지 않는다**.

## 테스트 시나리오
- **정상 흐름**: 라이브에서 "평가 실패: <urlopen error timed out>" → empirical 캡처 → datasource가 SEIBRO 해외 IP 차단 확정(logic/platform 무관) → fixer가 투명 스냅샷 폴백 → empirical가 라이브에서 정상+⚠표기 확인 → release가 커밋·(승인)push·Notion 로그. (선례: commit cad3b5a)
- **에러 흐름**: empirical가 라이브 재현 실패(소스 회복) → 로컬 diag도 정상 → "현재 정상, 과거 간헐 차단 추정"으로 보고하고 폴백 견고화만 제안, 무리한 수정/배포 안 함.
- **디자인 흐름**: "이 시안처럼 바꿔줘" → dashboard-designer가 토큰 기반으로 컴포넌트 적용 → 로컬 렌더 스크린샷 확인 → empirical가 기능 회귀 없음 확인 → release가 (승인)배포.

## 진화
매 실행 후 개선점 피드백을 받아 해당 에이전트/스킬/오케스트레이터를 갱신하고 CLAUDE.md 변경 이력에 기록한다.
