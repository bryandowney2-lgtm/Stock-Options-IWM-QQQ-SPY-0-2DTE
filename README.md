# Stock-Options IWM/QQQ/SPY 0–2 DTE Screener

A focused options screener for short-dated directional plays on the three
major index ETFs: **IWM, QQQ, SPY**. It scores each ETF on five factors built
for the 0–2 DTE timeframe, picks one strike per ETF, and ranks the three so
the best play of the day floats to the top.

This is a descendant of the original multi-factor swing screener, retuned from
the ground up — the old swing factors don't transfer to a gamma-driven,
intraday timeframe, so all five were replaced.

## What it is (and isn't)

**It is** a pre-market / open *setup* tool. With free yfinance data (~15 min
delayed), it tells you the bias and the strike to watch today.

**It is not** a live intraday trigger. The edge at 0DTE lives on the live tape.
Treat the output as a starting point and confirm on a real-time quote before
entering. **Nothing here is trade advice.**

## The five factors

| Factor | Weight | What it measures |
|---|---|---|
| Directional bias | 0.35 | Short-term trend on the underlying (EMA stack + VWAP proxy). Sets call vs put. |
| Relative strength | 0.20 | Which of the three ETFs is moving most today. |
| Premium value | 0.15 | Implied move vs realized — is premium cheap or rich? |
| Liquidity | 0.20 | Bid/ask spread + open interest + volume on the chosen strike. The 0DTE trade-killer. |
| Strike quality | 0.10 | How close the chosen strike's delta is to target. |

Profile is **lean-directional** — momentum carries the score. Retune in
`config.py`; weights must sum to 1.0.

## A note on 0DTE delta

At exactly 0 DTE in the final hours, the delta curve is a near-cliff: ATM is
~0.50 and the neighbouring strikes snap toward 0 or 1. `TARGET_DELTA = 0.45`
is most meaningful at 1–2 DTE; at 0 DTE the screener will sensibly land near
ATM. That's the nature of the instrument, not a bug.

## Run it

```bash
pip install -r requirements.txt
python screener.py
```

Outputs to console and writes `latest_signal.md`. Toggle either in `config.py`.

Offline sanity check (no network needed):

```bash
python test_offline.py
```

## Scheduled runs

`.github/workflows/screener.yml` runs on weekdays shortly after the open and
commits `latest_signal.md` back to the repo. The cron is **UTC and does not
shift for daylight saving** — see the comment in the workflow. Trigger it
manually any time from the Actions tab (`workflow_dispatch`).

## Swapping the data source (yfinance → Tradier)

The data layer is isolated behind a single interface so nothing in the scoring
logic cares where data comes from. To move to Tradier later:

1. Write `data_providers/tradier_provider.py` implementing the three methods in
   `data_providers/base.py` (`get_intraday_bars`, `get_expiries`, `get_chain`).
   Tradier returns Greeks directly, so you can populate `delta` and skip the
   Black-Scholes step.
2. Add one line to `PROVIDERS` in `data_providers/__init__.py`.
3. Set `PROVIDER = "tradier"` in `config.py` and add your API key as a GitHub
   secret.

No other file changes.

## Layout

```
config.py                  all tunables (universe, weights, DTE, thresholds)
screener.py                entrypoint — run this
scoring.py                 five-factor engine + strike selection
greeks.py                  Black-Scholes delta (yfinance gives IV, not delta)
data_providers/
  base.py                  the provider contract + OptionContract
  yfinance_provider.py     free, delayed, default
  __init__.py              provider registry
test_offline.py            offline pipeline test with synthetic data
.github/workflows/         scheduled run
```
