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

    df = fdr.DataReader(ticker, start, end)
    if df.empty or "Close" not in df.columns:
        raise RuntimeError(f"종목 {ticker}의 시세를 가져오지 못했습니다 ({start} ~ {end}).")
    return df["Close"].dropna()


def peer_group_volatility(
    peer_group: list[dict],
    valuation_date,
    lookback_years: float = 1.0,
    trading_days: int = TRADING_DAYS,
) -> dict:
    """피어그룹 각 사의 변동성을 계산하고 산술평균을 반환한다.

    peer_group 형식: [{"name": "안랩", "ticker": "053800"}, ...]
    (입력 파일 data/valuation_inputs_template.json의 volatility_estimation.peer_group)

    반환 dict에는 적용 변동성(mean_volatility)과 함께
    피어별 산출 내역이 담겨 보고서에 그대로 수록된다.
    """
    if not peer_group:
        raise ValueError("피어그룹이 비어 있습니다.")

    # 수집 기간: 평가기준일로부터 lookback_years만큼 소급
    end = pd.Timestamp(valuation_date)
    start = end - pd.Timedelta(days=round(lookback_years * 365.25))

    peers = []
    for peer in peer_group:
        prices = fetch_close_prices(peer["ticker"], start, end)
        vol = annualized_volatility(prices, trading_days)
        # 보고서 수록용 산출 내역 (어떤 데이터로 어떻게 계산했는지 남긴다)
        peers.append(
            {
                "name": peer.get("name", peer["ticker"]),
                "ticker": peer["ticker"],
                "volatility": vol,
                "observations": int(len(prices)),
                "first_date": str(prices.index[0].date()),
                "last_date": str(prices.index[-1].date()),
            }
        )

    # 피어 변동성의 산술평균 = 기초자산 변동성으로 적용할 값
    mean_vol = float(np.mean([p["volatility"] for p in peers]))
    return {
        "mean_volatility": mean_vol,
        "peers": peers,
        "lookback_years": lookback_years,
        "trading_days": trading_days,
        "period": {"start": str(start.date()), "end": str(end.date())},
        "data_source": "FinanceDataReader (KRX 시세)",
    }
