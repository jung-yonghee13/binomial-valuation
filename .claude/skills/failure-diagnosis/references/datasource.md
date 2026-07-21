# 외부 데이터 계층 진단 참조

담당: datasource-diagnostician. 대상: `valuation/seibro.py`(국고채, urllib), `valuation/volatility.py`(피어 주가, FinanceDataReader).

## 왜 여기서 실패가 잦은가
파이프라인에서 결정론적이지 않은 유일한 부분이 외부 수집이다. 배포 서버(Streamlit Cloud)는 해외(미국) IP라서 **국내 전용 SEIBRO에 못 닿는다**. 로컬(한국 IP)에선 재현이 안 되므로 "갑자기·계속·입력 무관·클라우드에서만" 패턴이 전형이다. (선례: `<urlopen error timed out>`, commit cad3b5a에서 스냅샷 폴백으로 해결)

## 에러 지문
| 지문 | 소스 | 함의 |
|---|---|---|
| `<urlopen error timed out>` / `URLError` / socket timeout | SEIBRO(`urllib.request.urlopen`) | 국고채 수집 차단/지연 |
| `HTTPSConnectionPool ... Read timed out` / `ConnectionError` | FinanceDataReader(requests) | 시세 소스 문제 |
| `RuntimeError: ...수익률을 찾지 못했습니다` | SEIBRO 파싱 | 응답은 왔으나 국고채권 행 없음(휴일 소급 소진/포맷 변경) |
| `ValueError: 가격 데이터가 부족합니다` | volatility | 관측치<30(상장폐지·거래정지·기간 부족) |

## 실행 순서 단서
`run_valuation.run`은 **변동성(FDR) → 무위험이자율(SEIBRO)** 순. 그래서 SEIBRO 에러가 떴다면 FDR은 이미 통과 = 그 순간 FDR은 도달 가능. FDR 에러면 SEIBRO엔 도달조차 안 함.

## 실측 절차 (코드 변경 없이)
```
python - <<'PY'
from valuation import seibro, volatility
from datetime import date
d = date.today().isoformat()
try:
    c = seibro.fetch_treasury_curve(d); print("SEIBRO OK", c["date"], len(c["maturities"]))
except Exception as e: print("SEIBRO FAIL", type(e).__name__, e)
for tk in ["053800","012510","030520","053580","131370"]:
    try:
        s = volatility.fetch_close_prices(tk, "2025-07-01", d); print("FDR OK", tk, len(s))
    except Exception as e: print("FDR FAIL", tk, type(e).__name__, e)
PY
```
- 여러 번 호출해 성공/실패가 섞이면 **레이트리밋·일시장애**, 항상 실패면 **하드 차단**.
- 로컬에서 되는데 라이브가 안 되면(empirical-tester 대조) → 해외 IP 차단 확정.

## 점검 포인트
- `seibro._fetch_xml`의 timeout, 휴일 소급 루프(`max_lookback_days`)의 총 대기시간·재시도 유무.
- SEIBRO 실패 시 `data/fallback_ytm_curve.json` 폴백 동작 + `⚠` 투명 표기 여부(`resolve_risk_free`).
- FDR엔 폴백이 없음 → 배포 환경에서 FDR까지 막히면 변동성 auto가 죽는다(잠재 리스크로 보고).

## 권고 방향 (fixer에게)
- 하드 차단: 번들 스냅샷 폴백(투명 표기) 또는 한국 리전 호스팅 제안.
- 지연: timeout 단축 + 폴백, 필요 시 짧은 재시도.
- 조용한 대체 금지: 폴백 값은 반드시 결과·보고서에 근거(날짜·출처)와 함께 노출.
