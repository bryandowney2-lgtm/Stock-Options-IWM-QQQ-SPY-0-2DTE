"""Five-factor scoring for 0-2 DTE directional plays on IWM/QQQ/SPY.

Each factor returns 0..1. The composite is the weighted sum. The screener
picks ONE strike per ETF (the best-fitting contract on the chosen side),
then ranks the three ETFs against each other.

Factors (replacing the old swing-trade five):
  1. directional_bias  - short-term trend on the underlying -> call or put side
  2. relative_strength - this ETF's momentum vs the other two today
  3. premium_value     - implied move vs realized; cheap premium scores higher
  4. liquidity         - spread + OI + volume on the chosen strike
  5. strike_quality    - how close the strike's delta is to target
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import numpy as np
import pandas as pd

import config as C
from data_providers.base import OptionContract
from greeks import bs_delta


# ---------- underlying-level signals (computed once per ticker) ----------

@dataclass
class Underlying:
    symbol: str
    spot: float
    bias: float          # -1 (bearish) .. +1 (bullish)
    momentum: float      # raw recent return, for relative-strength ranking
    realized_vol: float  # annualized, from intraday bars
    bars: pd.DataFrame


def analyze_underlying(symbol: str, bars: pd.DataFrame) -> Underlying:
    close = bars["Close"].dropna()
    spot = float(close.iloc[-1])

    # EMAs for trend stack
    ema_fast = close.ewm(span=5).mean().iloc[-1]
    ema_slow = close.ewm(span=10).mean().iloc[-1]

    # VWAP proxy over the session window we have
    tp = (bars["High"] + bars["Low"] + bars["Close"]) / 3
    vwap = float((tp * bars["Volume"]).sum() / max(bars["Volume"].sum(), 1))

    # bias: blend of EMA stack and price-vs-vwap, squashed to -1..1
    ema_signal = np.tanh((ema_fast - ema_slow) / spot * 100)
    vwap_signal = np.tanh((spot - vwap) / spot * 100)
    bias = float(np.clip(0.6 * ema_signal + 0.4 * vwap_signal, -1, 1))

    # momentum: return over the recent window (last ~1.5 sessions of 15m bars)
    lookback = min(len(close) - 1, 26)
    momentum = float(close.iloc[-1] / close.iloc[-1 - lookback] - 1) if lookback > 0 else 0.0

    # realized vol: annualized stdev of bar returns
    rets = np.log(close / close.shift(1)).dropna()
    bars_per_year = 252 * 26  # ~26 fifteen-min bars per session
    realized_vol = float(rets.std() * np.sqrt(bars_per_year)) if len(rets) > 2 else 0.0

    return Underlying(symbol, spot, bias, momentum, realized_vol, bars)


# ---------- per-factor scores (0..1) ----------

def score_directional_bias(u: Underlying) -> float:
    """Strength of the directional signal, regardless of side."""
    return abs(u.bias)


def score_relative_strength(u: Underlying, all_momos: list[float]) -> float:
    """Rank this ETF's momentum magnitude against the cohort today."""
    mags = [abs(m) for m in all_momos]
    hi = max(mags) if mags else 0.0
    if hi == 0:
        return 0.5
    return abs(u.momentum) / hi


def score_premium_value(u: Underlying, contract: OptionContract) -> float:
    """Cheap implied vol vs realized scores higher (better for buying premium).
    Ratio realized/implied: >1 means implied is cheap relative to recent moves."""
    if contract.iv <= 0:
        return 0.3
    ratio = u.realized_vol / contract.iv
    # map ratio 0.5..1.5 onto 0..1, clip outside
    return float(np.clip((ratio - 0.5), 0, 1))


def score_liquidity(contract: OptionContract) -> float:
    """Spread is the dominant term at 0DTE; OI and volume support it."""
    # spread component: 0% spread -> 1.0, at/over MAX_SPREAD_PCT -> ~0
    spread_score = max(0.0, 1 - contract.spread_pct / C.MAX_SPREAD_PCT)
    oi_score = min(1.0, contract.open_interest / (C.MIN_OPEN_INTEREST * 10))
    vol_score = min(1.0, contract.volume / (C.MIN_VOLUME * 20))
    return float(0.6 * spread_score + 0.25 * oi_score + 0.15 * vol_score)


def score_strike_quality(contract: OptionContract) -> float:
    """How close the contract's delta is to target."""
    if contract.delta is None:
        return 0.3
    dist = abs(abs(contract.delta) - C.TARGET_DELTA)
    return float(max(0.0, 1 - dist / C.DELTA_TOLERANCE))


# ---------- strike picking ----------

def _dte(expiry: str) -> int:
    e = dt.datetime.strptime(expiry, "%Y-%m-%d").date()
    return (e - dt.date.today()).days


def pick_contract(u: Underlying, chain: list[OptionContract],
                  expiry: str) -> OptionContract | None:
    """Choose the side from bias, then the strike whose delta is closest
    to TARGET_DELTA among liquid candidates."""
    side = "call" if u.bias >= 0 else "put"
    t_years = max(_dte(expiry), 0) / 252 + 1e-6

    candidates = []
    for c in chain:
        if c.kind != side:
            continue
        if c.iv <= 0 or c.mid <= 0:
            continue
        c.delta = bs_delta(u.spot, c.strike, t_years, c.iv, c.kind, C.RISK_FREE_RATE)
        candidates.append(c)

    if not candidates:
        return None

    # prefer ones that pass liquidity guards; fall back to all if none pass
    liquid = [c for c in candidates
              if c.spread_pct <= C.MAX_SPREAD_PCT
              and c.open_interest >= C.MIN_OPEN_INTEREST
              and c.volume >= C.MIN_VOLUME]
    pool = liquid if liquid else candidates

    # drop pinned extremes (delta ~0 or ~1 carry no directional/gamma value)
    in_band = [c for c in pool if 0.05 < abs(c.delta) < 0.95]
    if in_band:
        pool = in_band

    return min(pool, key=lambda c: abs(abs(c.delta) - C.TARGET_DELTA))


# ---------- composite ----------

@dataclass
class Signal:
    symbol: str
    side: str
    spot: float
    expiry: str
    contract: OptionContract
    factors: dict
    composite: float
    liquid_ok: bool


def build_signal(u: Underlying, contract: OptionContract, expiry: str,
                 all_momos: list[float]) -> Signal:
    factors = {
        "directional_bias": score_directional_bias(u),
        "relative_strength": score_relative_strength(u, all_momos),
        "premium_value": score_premium_value(u, contract),
        "liquidity": score_liquidity(contract),
        "strike_quality": score_strike_quality(contract),
    }
    composite = sum(C.WEIGHTS[k] * v for k, v in factors.items())
    liquid_ok = (contract.spread_pct <= C.MAX_SPREAD_PCT
                 and contract.open_interest >= C.MIN_OPEN_INTEREST
                 and contract.volume >= C.MIN_VOLUME)
    return Signal(
        symbol=u.symbol,
        side="call" if u.bias >= 0 else "put",
        spot=u.spot,
        expiry=expiry,
        contract=contract,
        factors=factors,
        composite=composite,
        liquid_ok=liquid_ok,
    )
