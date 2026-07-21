"""피어그룹 주가 기반 역사적 변동성 산출.

[이 파일이 하는 일]
비상장 기초자산의 변동성은 직접 관찰할 수 없으므로,
유사 상장기업(피어그룹, 대용기업) 여러 곳의 주가 변동성을 계산해 평균낸다.

[산출 절차 — 실무 방식 그대로]
1. 피어 각 사의 영업일 기준 일별 종가를 수집 (기본: 평가기준일로부터 소급 1년)
2. 일별 로그수익률 ln(오늘 종가 / 어제 종가) 계산
3. 로그수익률의 표본표준편차 × √252 = 연환산 변동성
   (252 = 1년 영업일 수. 일 단위 변동성을 연 단위로 확대하는 관행적 계수)
4. 피어 5개사 변동성의 산술평균 → 기초자산 변동성으로 사용

산출 내역(피어별 변동성, 관측치 수, 수집 기간, 출처)은 모두 반환되어
보고서 '주요변수 및 가정' 장에 그대로 수록된다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252     # 연환산 계수 (1년 영업일 수)
MIN_OBSERVATIONS = 30  # 이보다 관측치가 적으면 통계적으로 무의미하므로 계산 거부
MIN_PEER_SUCCESS = 2   # 피어그룹 부분실패 허용 시 최소 성공 피어 수 (미달이면 폴백/실패)


class PriceFetchError(RuntimeError):
    """시세 수집 실패를 나타내는 예외 (네트워크 차단·타임아웃·빈 응답 등).

    raw requests/urllib 예외를 이 타입으로 래핑해, 상위(resolve_volatility)가
    SEIBRO 폴백과 동일한 방식으로 일관되게 잡아 스냅샷 폴백으로 넘어갈 수 있게 한다.
    RuntimeError를 상속하므로 기존 `except RuntimeError` 경로와도 호환된다.
    """


def annualized_volatility(prices, trading_days: int = TRADING_DAYS) -> float:
    """일별 종가 시계열에서 연환산 역사적 변동성을 계산한다.

    수식: 변동성 = std( ln(P_t / P_{t-1}) ) × √252
    """
    p = np.asarray(prices, dtype=float)
    p = p[~np.isnan(p)]  # 결측치(휴장 등) 제거
    if len(p) < MIN_OBSERVATIONS:
        raise ValueError(
            f"가격 데이터가 부족합니다: {len(p)}개 (최소 {MIN_OBSERVATIONS}영업일 필요)"
        )
    if np.any(p <= 0):
        raise ValueError("가격 데이터에 0 이하의 값이 있습니다.")

    # 로그수익률: np.diff(np.log(p)) = ln(P_t) - ln(P_{t-1}) = ln(P_t / P_{t-1})
    log_returns = np.diff(np.log(p))
    # ddof=1: 표본표준편차 (모집단이 아닌 표본이므로 n-1로 나눔)
    return float(log_returns.std(ddof=1) * np.sqrt(trading_days))


def fetch_close_prices(ticker: str, start, end) -> pd.Series:
    """KRX 종목의 일별 종가를 수집한다 (FinanceDataReader 사용).

    ticker는 6자리 종목코드 (예: 안랩 "053800").
    """
    try:
        import FinanceDataReader as fdr
    except ImportError as exc:
        raise RuntimeError(
            "시세 수집에는 FinanceDataReader가 필요합니다: pip install finance-datareader"
        ) from exc

    try:
        df = fdr.DataReader(ticker, start, end)
    except Exception as exc:
        # FinanceDataReader 내부는 requests 계열 예외(ConnectionError/Timeout 등)를
        # 그대로 누출한다. 배포 환경(해외 IP) 차단·타임아웃을 일관된 타입으로 래핑해
        # 상위에서 SEIBRO 폴백과 동일하게 잡을 수 있게 한다.
        raise PriceFetchError(
            f"종목 {ticker}의 시세 수집에 실패했습니다 ({type(exc).__name__}: {exc})."
        ) from exc
    if df.empty or "Close" not in df.columns:
        raise PriceFetchError(f"종목 {ticker}의 시세를 가져오지 못했습니다 ({start} ~ {end}).")
    return df["Close"].dropna()


def peer_group_volatility(
    peer_group: list[dict],
    valuation_date,
    lookback_years: float = 1.0,
    trading_days: int = TRADING_DAYS,
    min_success: int = MIN_PEER_SUCCESS,
) -> dict:
    """피어그룹 각 사의 변동성을 계산하고 산술평균을 반환한다.

    peer_group 형식: [{"name": "안랩", "ticker": "053800"}, ...]
    (입력 파일 data/valuation_inputs_template.json의 volatility_estimation.peer_group)

    부분 실패 허용: 일부 피어의 시세 수집이 실패해도 성공한 피어들만으로 평균을
    산출하고, 실패한 피어는 사유와 함께 반환 dict의 failed_peers에 기록한다.
    단, 성공한 피어가 min_success개(피어 총수보다 크면 총수로 하향) 미만이면
    통계적으로 무의미하므로 PriceFetchError로 실패시킨다(상위에서 스냅샷 폴백).

    반환 dict에는 적용 변동성(mean_volatility)과 함께
    피어별 산출 내역이 담겨 보고서에 그대로 수록된다.
    """
    if not peer_group:
        raise ValueError("피어그룹이 비어 있습니다.")

    # 수집 기간: 평가기준일로부터 lookback_years만큼 소급
    end = pd.Timestamp(valuation_date)
    start = end - pd.Timedelta(days=round(lookback_years * 365.25))

    peers = []
    failed_peers = []
    for peer in peer_group:
        name = peer.get("name", peer["ticker"])
        try:
            prices = fetch_close_prices(peer["ticker"], start, end)
            vol = annualized_volatility(prices, trading_days)
        except (PriceFetchError, ValueError) as exc:
            # 개별 피어 실패(시세 차단·관측치 부족 등)는 전체를 중단하지 않는다.
            failed_peers.append(
                {"name": name, "ticker": peer["ticker"], "reason": str(exc)}
            )
            continue
        # 보고서 수록용 산출 내역 (어떤 데이터로 어떻게 계산했는지 남긴다)
        peers.append(
            {
                "name": name,
                "ticker": peer["ticker"],
                "volatility": vol,
                "observations": int(len(prices)),
                "first_date": str(prices.index[0].date()),
                "last_date": str(prices.index[-1].date()),
            }
        )

    required = min(min_success, len(peer_group))
    if len(peers) < required:
        reasons = "; ".join(f"{f['name']}({f['ticker']}): {f['reason']}" for f in failed_peers)
        raise PriceFetchError(
            f"피어그룹 시세 수집 실패: {len(peers)}/{len(peer_group)}개만 성공 "
            f"(최소 {required}개 필요). 실패 내역 → {reasons}"
        )

    # 피어 변동성의 산술평균 = 기초자산 변동성으로 적용할 값
    mean_vol = float(np.mean([p["volatility"] for p in peers]))
    return {
        "mean_volatility": mean_vol,
        "peers": peers,
        "failed_peers": failed_peers,
        "lookback_years": lookback_years,
        "trading_days": trading_days,
        "period": {"start": str(start.date()), "end": str(end.date())},
        "data_source": "FinanceDataReader (KRX 시세)",
    }


def own_stock_volatility(
    ticker: str,
    name: str,
    valuation_date,
    lookback_years: float = 1.0,
    trading_days: int = TRADING_DAYS,
) -> dict:
    """상장기업의 자기 주가로 역사적 변동성을 계산한다.

    기초자산이 상장주식이면 피어그룹이 필요 없이 해당 종목의 일별 종가로
    변동성을 직접 산출한다. 반환 dict는 peer_group_volatility()와 같은 형식이라
    보고서·결과 처리에서 동일하게 다룰 수 있다 (peers에 자기 종목 1건만 담김).
    """
    ticker = str(ticker).strip().zfill(6)
    end = pd.Timestamp(valuation_date)
    start = end - pd.Timedelta(days=round(lookback_years * 365.25))

    prices = fetch_close_prices(ticker, start, end)
    vol = annualized_volatility(prices, trading_days)
    entry = {
        "name": name or ticker,
        "ticker": ticker,
        "volatility": vol,
        "observations": int(len(prices)),
        "first_date": str(prices.index[0].date()),
        "last_date": str(prices.index[-1].date()),
    }
    return {
        "mean_volatility": vol,
        "peers": [entry],  # 자기 종목 1건 (보고서 표를 동일하게 렌더링하기 위함)
        "lookback_years": lookback_years,
        "trading_days": trading_days,
        "period": {"start": str(start.date()), "end": str(end.date())},
        "data_source": "FinanceDataReader (KRX 시세) — 기초자산 자기 주가",
        "own_stock": True,
    }
