---
name: failure-diagnosis
description: 이항모형 가치평가 앱의 실패를 계층별로 분리 진단하는 방법. 외부 데이터(SEIBRO·FinanceDataReader), 입력검증·계산엔진(run_valuation·binomial·monte_carlo), 플랫폼(Streamlit·배포·PDF)의 3개 계층을 각각의 참조 문서로 파고든다. datasource/logic/platform-diagnostician이 담당 계층 진단 시 사용. 원인 특정·근본 진단·계층 분리가 필요할 때 사용.
---

# 계층별 실패 진단

empirical-tester가 잡은 실제 에러를 받아 **어느 계층의 무엇이** 원인인지 확정한다. 코드는 바꾸지 않는다 — 진단만 한다(수정은 root-cause-fix).

## 진단 공통 원칙 (Why 중심)
- **에러 지문에서 출발**: 예외 타입·메시지가 계층을 강하게 가리킨다. 지문과 실제 코드 경로를 대조해 확정한다. 추측으로 계층을 넘기지 않는다.
- **재현이 곧 증거**: 의심 원인을 최소 케이스로 재현해 "그것이 맞다"를 실측으로 보인다. 재현 안 되면 신뢰도를 낮춰 보고.
- **경계면을 본다**: 실패는 종종 계층 사이(UI dict ↔ 엔진 키, 수집 반환 ↔ 소비 형식)에서 난다. 한쪽만 보지 말고 넘겨주는 값의 shape을 양쪽에서 비교.
- **환경 의존 구분**: 로컬 재현 여부로 "코드 결함"과 "환경 의존 실패"를 나눈다. 로컬 성공+라이브 실패 = 환경(네트워크/설정).
- **무관도 결론이다**: 담당 계층이 원인 아니면 근거와 함께 "이 계층 무관"을 명시해, fixer가 다른 계층 결론과 병합하게 한다.

## 계층별 상세 (담당 계층 참조만 로드)
- 외부 데이터: `references/datasource.md` — SEIBRO(urllib)·FinanceDataReader(requests), 해외 IP 차단·타임아웃·레이트리밋·폴백.
- 입력검증·계산: `references/logic.md` — run_valuation의 ValueError 지점, binomial·monte_carlo·spot_rate·변동성 수치 예외, 경계값.
- 플랫폼: `references/platform.md` — Streamlit 세션·rerun, requirements/packages/config, PDF(chromium 헤드리스), 로컬↔클라우드 차이.

## 산출물 (각 diagnostician)
`_workspace/02_diag_{layer}.md` 에 기록:
1. **판정**: 이 계층이 원인인가 (원인 확정 / 기여 / 무관) + 신뢰도(상/중/하)
2. **근거**: 에러 지문, 실측 재현 결과, 관련 코드 지점(file:line)
3. **권고**: root-cause-fix가 취할 수정 방향(폴백/명확한 에러/타임아웃/구조 수정 등)
4. **교차검토 메모**: 다른 계층과 겹치거나 상충하는 부분

## 교차 검토
3명의 diagnostician은 결론을 `SendMessage`로 교차 검토한다. 상충하면 empirical-tester의 실제 관찰을 최종 판정 기준으로 삼는다. 여러 계층이 동시 원인일 수 있으니 "단일 범인" 강박을 피한다.
