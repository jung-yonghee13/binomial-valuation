---
name: release-and-document
description: 검증된 수정을 커밋·push해 Streamlit Cloud 자동 재배포를 트리거하고, 재배포 반영을 라이브에서 확인하며, Notion 프로젝트 페이지의 업데이트 로그·설명을 갱신하는 방법. release-manager가 릴리스·문서 반영 시 사용. 커밋·배포·푸시·Notion 반영·업데이트 로그 갱신이 필요할 때 사용. 외부 반영은 사용자 승인 후.
---

# 릴리스·배포·문서 반영

empirical-tester 검증(`_workspace/05_empirical_verify.md`)을 통과한 변경만 반영한다. **미검증 변경은 배포하지 않는다.**

## 절차
### 1. 커밋 (로컬)
- 논리 단위로 커밋. 메시지: 한국어 제목 한 줄 + 본문(원인 → 해결 → 검증 근거).
- 끝에 반드시: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- 무엇을 커밋했는지 사용자에게 보고.

### 2. 배포 (push) — 사용자 승인 후
- `git push origin master` → Streamlit Community Cloud 자동 재배포.
- push는 공개 저장소 반영이므로 **무엇을 반영할지 요약 보고 후 승인**을 받고 실행.
- 원격에 선행 커밋이 있으면(push 거부) `git fetch` → `git rebase origin/master` → 재push. rebase로 **커밋 해시가 바뀌면** 문서에 옮길 해시를 갱신.

### 3. 재배포 확인
- 라이브 앱을 새로고침해 실패하던 시나리오가 정상/폴백으로 바뀌었는지 확인(empirical-tester 검증과 일치).
- 반영 지연 시 잠시 후 재확인. `APP_BUILD`를 올린 커밋이면 화면 build 표기로 판별.

### 4. Notion 문서 반영 — 사용자 승인 후
- 페이지: "binomial-valuation — CRR 이항모형 기반 밸류에이션 자동화" (id `39b9016d-66a9-8156-b54a-f4651ef14cb7`).
- **업데이트 로그** 표 최상단에 행 추가: `일자 | 변경 요약 | \`커밋해시\``. 기존에 같은 행이 있는지 먼저 확인(중복 금지).
- 변경이 동작 설명에 영향을 주면 관련 접이식(예: "Seibro 자동 수집…") 설명도 사실에 맞게 갱신. `notion-update-page`의 `update_content`로 최소 편집.
- 문서는 코드 사실과 일치해야 한다(과장·미검증 서술 금지).

## 안전 규칙 (외부 행동)
- `git push`와 Notion 수정은 공개/외부 반영 → **사용자 승인 필수**. 승인 요청 시 정확히 무엇이 바뀌는지(파일·커밋·Notion 행) 요약 제시.
- 커밋(로컬)은 승인 없이 가능하나 결과 보고.

## 산출물
`_workspace/06_release.md`: 커밋 해시, push/재배포 결과(라이브 확인 포함), Notion 갱신 내역. 사용자에게 최종 요약.

## 에러 핸들링
- rebase 충돌이 복잡하면 멈추고 사용자에게 보고(임의 해결 금지).
- 재배포가 계속 반영 안 되면 Streamlit Cloud 수동 재부팅(Manage app) 안내.
