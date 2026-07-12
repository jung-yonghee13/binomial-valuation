"""피어그룹 주가 기반 역사적 변동성 산출.

피어그룹(대용기업) 각 사의 영업일 기준 일별 종가를 수집하여
일별 로그수익률 표준편차를 연환산(√252)한 뒤 산술평균한다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252
MIN_OBSERVATIONS = 30


def annualized_volatility(prices, trading_days: int = TRADING_DAYS) -> float:
    """일별 종가 시계열에서 연환산 역사적 변동성을 계산한다."""
    p = np.asarray(prices, dtype=float)
    p = p[~np.isnan(p)]
    if len(p) < MIN_OBSERVATIONS:
        raise ValueError(
            f"가격 데이터가 부족합니다: {len(p)}개 (최소 {MIN_OBSERVATIONS}영업일 필요)"
        )
    if np.any(p <= 0):
        raise ValueError("가격 데이터에 0 이하의 값이 있습니다.")
    log_returns = np.diff(np.log(p))
    return float(log_returns.std(ddof=1) * np.sqrt(trading_days))


def fetch_close_prices(ticker: str, start, end) -> pd.Series:
    """KRX 종목의 일별 종가를 수집한다 (FinanceDataReader 사용)."""
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

    peer_group: [{"name": "...", "ticker": "..."}, ...]
    반환 dict는 보고서 '주요변수 및 가정' 장에 수록할 산출 내역을 포함한다.
    """
    if not peer_group:
        raise ValueError("피어그룹이 비어 있습니다.")

    end = pd.Timestamp(valuation_date)
    start = end - pd.Timedelta(days=round(lookback_years * 365.25))

    peers = []
    for peer in peer_group:
        prices = fetch_close_prices(peer["ticker"], start, end)
        vol = annualized_volatility(prices, trading_days)
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

    mean_vol = float(np.mean([p["volatility"] for p in peers]))
    return {
        "mean_volatility": mean_vol,
        "peers": peers,
        "lookback_years": lookback_years,
        "trading_days": trading_days,
        "period": {"start": str(start.date()), "end": str(end.date())},
        "data_source": "FinanceDataReader (KRX 시세)",
    }
