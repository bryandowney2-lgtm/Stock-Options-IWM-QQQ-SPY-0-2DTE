"""yfinance provider. Free, no key, ~15min delayed. Good for a pre-market
/ open setup tool running on a schedule.

yfinance gives IV but not delta — the screener computes delta from IV via
Black-Scholes, so leaving delta=None here is correct.
"""
from __future__ import annotations

import pandas as pd
import yfinance as yf

from .base import DataProvider, OptionContract


def _f(v, default=0.0):
    try:
        if v is None or pd.isna(v):
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _i(v, default=0):
    try:
        if v is None or pd.isna(v):
            return default
        return int(v)
    except (TypeError, ValueError):
        return default


class YFinanceProvider(DataProvider):
    def __init__(self):
        self._cache: dict[str, yf.Ticker] = {}

    def _ticker(self, symbol: str) -> yf.Ticker:
        if symbol not in self._cache:
            self._cache[symbol] = yf.Ticker(symbol)
        return self._cache[symbol]

    def get_intraday_bars(self, symbol, period="5d", interval="15m"):
        df = self._ticker(symbol).history(period=period, interval=interval)
        if df.empty:
            raise RuntimeError(f"No intraday bars returned for {symbol}")
        return df

    def get_expiries(self, symbol):
        exp = self._ticker(symbol).options
        if not exp:
            raise RuntimeError(f"No option expiries returned for {symbol}")
        return list(exp)

    def get_chain(self, symbol, expiry):
        ch = self._ticker(symbol).option_chain(expiry)
        out: list[OptionContract] = []
        for kind, frame in (("call", ch.calls), ("put", ch.puts)):
            for _, r in frame.iterrows():
                out.append(OptionContract(
                    symbol=symbol,
                    expiry=expiry,
                    strike=_f(r.get("strike")),
                    kind=kind,
                    bid=_f(r.get("bid")),
                    ask=_f(r.get("ask")),
                    last=_f(r.get("lastPrice")),
                    iv=_f(r.get("impliedVolatility")),
                    open_interest=_i(r.get("openInterest")),
                    volume=_i(r.get("volume")),
                ))
        return out
