# 입력검증·계산 엔진 계층 진단 참조

담당: logic-diagnostician. 대상: `valuation/run_valuation.py`, `binomial.py`, `monte_carlo.py`, `risk_free.py`, `volatility.py`(계산부), `payoffs.py`.

## 특징
이 계층 실패는 **환경과 무관하게 로컬에서도 100% 재현**된다. 로컬 성공+라이브만 실패면 이 계층이 아니다(datasource/platform 의심).

## 입력 검증 예외 지점 (`run_valuation`)
| 예외 | 조건 | 위치 |
|---|---|---|
| `ValueError: 만기일(...)이 평가기준일(...) 이후여야 합니다` | 만기 ≤ 평가기준일 | `years_between` |
| `ValueError: exercise_scope은 0 초과 1 이하...` | 행사범위 범위 밖 | `run` |
| `ValueError: 보유자 행사비율은 0 초과 1 이하...` / `...합계가 100%를 초과` | 보유자 비율 | `run` |
| `ValueError: volatility는 숫자 또는 'auto'...` / `risk_free_rate는...` | 변수 형식 | `resolve_volatility`/`resolve_risk_free` |
| `ValueError: 비상장 기초자산의 변동성 자동 산출에는 피어그룹이 필요...` | 비상장+피어 없음 | `resolve_volatility` |
| `NotImplementedError: 현재 콜옵션 평가만 지원...` | option_type≠call | `run` |
| `ValueError: 주요변수 '...'가 입력되지 않았습니다` | 필수값 누락 | `run` |

## 계산 엔진 예외/이상
- `binomial.py`: 트리 파라미터(u/d/q) 비정상, 페이오프 함수 인자 불일치, 스텝 수 과대(메모리/시간)·과소(정확도).
- `monte_carlo.py`: 경로 수/시드, 교차검증 실패(`passed=False`는 예외가 아니라 결과 — 수렴/파라미터 점검 신호).
- `risk_free.spot_rate`/`step_forward_rates`: 곡선 보간 시 만기 범위 밖, maturities/yields 길이 불일치.
- `volatility.annualized_volatility`: 관측치<30(`MIN_OBSERVATIONS`), 가격≤0.
- 이상 결과 신호: 가치가 NaN/inf/음수, BS 수렴 테스트 이탈.

## 재현 절차
의심 입력을 최소 케이스로 만들어 확정한다:
```
python - <<'PY'
import json
from valuation import run_valuation
contract = json.load(open("data/sample_contract.json", encoding="utf-8-sig"))
inputs = json.load(open("data/valuation_inputs_template.json", encoding="utf-8-sig"))
inputs["inputs"]["valuation_date"] = "2026-06-30"
inputs["inputs"]["underlying_price_krw"] = 10000
# ↓ 의심 조건을 여기서 조작 (예: 만기<평가일, 비율 합계>1 등)
try:
    r = run_valuation.run(contract, inputs); print("OK", round(r["results"]["unit_value_krw"],2))
except Exception as e:
    import traceback; traceback.print_exc()
PY
```

## 경계면 확인 (UI ↔ 엔진)
`app.py`(run_clicked 블록)가 만드는 contract/inputs dict의 키·형식이 `run_valuation.run`이 읽는 키와 일치하는지 대조한다. 예: `exercise_scope`(app는 %/100), `holders` 형식, `maturity_date` 위치(inputs.inputs), `step_unit`("weekly"/None). 불일치는 조용한 오류를 만든다.

## 권고 방향 (fixer에게)
- **잘못된 입력**: 명확하고 행동 가능한 에러 메시지 + (가능하면) UI에서 사전 검증. cryptic 예외 금지.
- **로직 결함**: 최소 침습 수정 + 재현 케이스를 `tests/`에 회귀 테스트로 추가.
