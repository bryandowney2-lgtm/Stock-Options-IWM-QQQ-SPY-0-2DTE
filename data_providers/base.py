"""Data provider contract.

Every provider returns the SAME shapes so the screener never cares
where the data came from. Swap yfinance -> Tradier by writing a new
subclass and changing one line in config. Nothing else moves.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd


@dataclass
class OptionContract:
    symbol: str          # underlying, e.g. "SPY"
    expiry: str          # "YYYY-MM-DD"
    strike: float
    kind: str            # "call" or "put"
    bid: float
    ask: float
    last: float
    iv: float            # implied vol as a decimal, e.g. 0.18
    open_interest: int
    volume: int
    delta: float | None = None   # filled by screener if provider omits it

    @property
    def mid(self) -> float:
        if self.bid > 0 and self.ask > 0:
            return (self.bid + self.ask) / 2
        return self.last

    @property
    def spread_pct(self) -> float:
        """Bid/ask spread as % of mid. The 0DTE trade killer."""
        m = self.mid
        if m <= 0:
            return 999.0
        return (self.ask - self.bid) / m * 100


class DataProvider(ABC):
    """Implement these three methods and the screener works."""

    @abstractmethod
    def get_intraday_bars(self, symbol: str, period: str = "5d",
                          interval: str = "15m") -> pd.DataFrame:
        """OHLCV DataFrame indexed by datetime. Columns: Open High Low Close Volume."""

    @abstractmethod
    def get_expiries(self, symbol: str) -> list[str]:
        """All available expiry strings 'YYYY-MM-DD', ascending."""

    @abstractmethod
    def get_chain(self, symbol: str, expiry: str) -> list[OptionContract]:
        """Every contract for one expiry, calls and puts."""
