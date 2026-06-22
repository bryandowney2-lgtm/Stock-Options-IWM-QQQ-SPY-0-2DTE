"""Minimal Black-Scholes delta. yfinance gives IV but not delta, so we
compute it. Only delta is needed for strike selection."""
from __future__ import annotations

import math


def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs_delta(spot: float, strike: float, t_years: float, iv: float,
             kind: str, r: float = 0.043) -> float:
    """Black-Scholes delta. Returns +0..1 for calls, -1..0 for puts.

    Guards against the 0DTE degenerate case where t_years -> 0.
    """
    if spot <= 0 or strike <= 0 or iv <= 0:
        return 0.0
    # floor time so 0DTE doesn't divide by zero; ~1 hour minimum
    t = max(t_years, 1 / (252 * 6.5))
    d1 = (math.log(spot / strike) + (r + 0.5 * iv ** 2) * t) / (iv * math.sqrt(t))
    if kind == "call":
        return _norm_cdf(d1)
    return _norm_cdf(d1) - 1.0
