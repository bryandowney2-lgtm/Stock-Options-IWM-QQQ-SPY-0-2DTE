"""Offline test using synthetic data — validates the whole pipeline since
this sandbox can't reach Yahoo. Generates plausible bars + chains."""
import datetime as dt
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
import config as C
from data_providers.base import DataProvider, OptionContract
from scoring import analyze_underlying, pick_contract, build_signal, _dte


class MockProvider(DataProvider):
    SPOTS = {"IWM": 220.0, "QQQ": 480.0, "SPY": 590.0}
    DRIFT = {"IWM": 0.0008, "QQQ": -0.0005, "SPY": 0.0002}  # different biases

    def get_intraday_bars(self, symbol, period="5d", interval="15m"):
        n = 130
        rng = np.random.default_rng(hash(symbol) % 2**32)
        rets = rng.normal(self.DRIFT[symbol], 0.0015, n)
        close = self.SPOTS[symbol] * np.exp(np.cumsum(rets))
        idx = pd.date_range(end=dt.datetime.now(), periods=n, freq="15min")
        return pd.DataFrame({
            "Open": close * (1 - rng.normal(0, 0.0003, n)),
            "High": close * (1 + abs(rng.normal(0, 0.0006, n))),
            "Low": close * (1 - abs(rng.normal(0, 0.0006, n))),
            "Close": close,
            "Volume": rng.integers(1e5, 1e6, n),
        }, index=idx)

    def get_expiries(self, symbol):
        today = dt.date.today()
        return [(today + dt.timedelta(days=d)).strftime("%Y-%m-%d")
                for d in (0, 1, 2, 7, 14)]

    def __init__(self):
        self.spot_override = {}

    def get_chain(self, symbol, expiry):
        spot = self.spot_override.get(symbol, self.SPOTS[symbol])
        rng = np.random.default_rng((hash(symbol) ^ hash(expiry)) % 2**32)
        out = []
        # fine $1 strikes centered on the ACTUAL spot, like a real ETF chain
        for k in np.arange(round(spot) - 15, round(spot) + 15, 1.0):
            for kind in ("call", "put"):
                moneyness = abs(k - spot) / spot
                iv = 0.15 + moneyness * 2 + rng.normal(0, 0.01)
                mid = max(0.05, spot * 0.01 * np.exp(-moneyness * 20))
                spread = mid * rng.uniform(0.02, 0.12)
                out.append(OptionContract(
                    symbol=symbol, expiry=expiry, strike=round(float(k), 1), kind=kind,
                    bid=round(mid - spread / 2, 2), ask=round(mid + spread / 2, 2),
                    last=round(mid, 2), iv=round(iv, 4),
                    open_interest=int(rng.integers(50, 5000)),
                    volume=int(rng.integers(0, 2000)),
                ))
        return out


def main():
    p = MockProvider()
    unders = {s: analyze_underlying(s, p.get_intraday_bars(s)) for s in C.TICKERS}
    # tell the mock where each underlying actually drifted to, so its synthetic
    # strikes bracket spot the way a real chain always does
    for s, u in unders.items():
        p.spot_override[s] = u.spot
    momos = [u.momentum for u in unders.values()]
    sigs = []
    for s, u in unders.items():
        # use a 1-DTE expiry for the offline demo: at exactly 0 DTE the delta
        # curve is a near-cliff (ATM~0.5, neighbors snap to 0/1), which is real
        # market behavior but makes synthetic strikes look pinned. 1-DTE shows
        # the clean in-band selection. Live runs use the nearest qualifying expiry.
        exp = [e for e in p.get_expiries(s) if 1 <= _dte(e) <= C.MAX_DTE][0]
        c = pick_contract(u, p.get_chain(s, exp), exp)
        assert c is not None, f"no contract for {s}"
        assert c.delta is not None, f"delta not computed for {s}"
        sigs.append(build_signal(u, c, exp, momos))
    sigs.sort(key=lambda x: x.composite, reverse=True)

    print("PIPELINE OK — ranked signals:\n")
    for r, s in enumerate(sigs, 1):
        c = s.contract
        print(f"#{r} {s.symbol} {c.expiry} {c.strike:g}"
              f"{'C' if s.side=='call' else 'P'}  score {s.composite:.3f}  "
              f"side {s.side}  delta {c.delta:+.2f}  spread {c.spread_pct:.1f}%")
        assert 0 <= s.composite <= 1, "composite out of range"
        for k, v in s.factors.items():
            assert 0 <= v <= 1, f"factor {k} out of range: {v}"
    # weights sum check
    assert abs(sum(C.WEIGHTS.values()) - 1.0) < 1e-9, "weights don't sum to 1"
    print("\nAll assertions passed. Weights sum to 1.0. Factors in [0,1]. Composite in [0,1].")


if __name__ == "__main__":
    main()
