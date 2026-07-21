---
name: root-cause-fix
description: 이항모형 가치평가 앱의 진단된 근본 원인을 실제 코드로 수정하는 방법. "조용히 틀린 값 금지" 원칙에 따라 투명한 폴백·명확한 에러 메시지·회귀 방지를 함께 구현하고, 정상 경로 불변을 로컬 스모크 테스트로 보장한다. root-cause-fixer가 수정을 구현할 때 사용. 버그 수정·폴백 추가·에러 메시지 개선·방어 코드 작성 시 사용.
---

# 근본 원인 수정

진단(`_workspace/02_diag_*.md`)을 종합해 코드를 고친다. 목표는 "에러 안 나게"가 아니라 **"올바르게 동작하거나, 안 되면 정직하게 실패하게"**.

## 프로젝트 헌법 (반드시 지킴)
1. **조용히 틀린 값 금지** — 폴백/대체 데이터를 쓰면 결과·보고서에 사실과 근거(날짜·출처)를 노출한다.
   - 모범 사례(commit cad3b5a, `resolve_risk_free`): SEIBRO 실패 → `data/fallback_ytm_curve.json` 폴백 + `basis`/`curve_source`에 `⚠ 실시간 수집 실패 → 스냅샷 폴백(YYYY-MM-DD)` + `fallback_used=True`.
2. **명확한 에러** — 폴백도 불가하면 cryptic 예외 대신 사용자 행동을 담아 실패시킨다("무위험이자율을 직접 입력하거나 ytm_curve_file을 지정하세요").
3. **증상이 아닌 원인** — timeout을 늘려 가리지 말고, 왜 막히는지에 맞는 구조적 해법.
4. **정상 경로 불변** — 방어 코드가 로컬·정상 환경의 기존 동작·수치를 바꾸면 안 된다.
5. **계층 분리 유지** — 정책/폴백은 `resolve_*`(run_valuation)에, 순수 수집은 `seibro`/`volatility`에. 뒤섞지 않는다.

## 절차
1. 진단 종합. 상충하면 empirical-tester의 실제 관찰을 최종 기준으로.
2. 최소 침습 수정. 관련 파일만.
3. **스모크 테스트 (필수)** — 정상 경로 + 실패 경로 둘 다:
   ```
   # 정상 경로: 수치가 종전과 같은지
   python .claude/skills/reproduce-and-verify/scripts/diag_valuation.py
   # 실패 경로: 예외를 강제해 폴백/명확한 에러로 처리되는지
   python - <<'PY'
   import json, urllib.error
   from valuation import run_valuation, seibro
   contract = json.load(open("data/sample_contract.json", encoding="utf-8-sig"))
   inputs = json.load(open("data/valuation_inputs_template.json", encoding="utf-8-sig"))
   inputs["inputs"]["valuation_date"]="2026-06-30"; inputs["inputs"]["underlying_price_krw"]=11000
   seibro.fetch_treasury_curve = lambda *a,**k: (_ for _ in ()).throw(urllib.error.URLError("timed out"))
   r = run_valuation.run(contract, inputs); rf = r["valuation_inputs"]["risk_free_rate"]
   print("fallback_used=", rf.get("fallback_used"), "| basis=", rf["basis"])
   PY
   ```
   (Windows 콘솔 cp949로 한글/이모지 출력이 깨지면 `PYTHONIOENCODING=utf-8` 사용 — 로직이 아니라 표시 문제이므로 파일 확인으로 대체 가능.)
4. 회귀 방지: 진단이 남긴 최소 재현 케이스를 `tests/`에 추가할지 검토.

## 산출물
`_workspace/03_fix.md`: 무엇을·왜 고쳤는지, 변경 파일, 스모크 테스트 결과(정상/실패 경로), empirical-tester가 라이브에서 검증할 시나리오, 커밋 메시지 초안.

## 하지 말 것
- 정상 경로 수치를 바꾸는 변경(회귀). 발견 시 롤백 후 재설계.
- 조용한 폴백(표기 없이 대체값 사용). 진단 없이 여러 곳을 광범위 수정하는 것.
