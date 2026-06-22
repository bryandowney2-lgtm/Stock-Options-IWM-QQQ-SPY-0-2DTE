"""All tunables in one place. Edit here, not in the logic files."""

# ---- universe ----
TICKERS = ["IWM", "QQQ", "SPY"]

# ---- data source ----
PROVIDER = "yfinance"          # see data_providers/__init__.py

# ---- DTE window ----
MIN_DTE = 0
MAX_DTE = 2

# ---- factor weights (must sum to 1.0) ----
# Profile: LEAN DIRECTIONAL — momentum carries the score.
WEIGHTS = {
    "directional_bias": 0.35,   # short-term trend on the underlying
    "relative_strength": 0.20,  # which ETF is leading today
    "premium_value": 0.15,      # is implied move rich or cheap vs realized
    "liquidity": 0.20,          # spread + OI + volume on the chosen strike
    "strike_quality": 0.10,     # how well the strike fits the expected move
}

# ---- strike selection ----
TARGET_DELTA = 0.45            # slightly OTM directional; ~ATM. raise toward 0.5 for ATM
DELTA_TOLERANCE = 0.15         # acceptable band around target

# ---- liquidity guards (a candidate failing these is penalized hard) ----
MAX_SPREAD_PCT = 15.0          # bid/ask spread as % of mid
MIN_OPEN_INTEREST = 100
MIN_VOLUME = 10

# ---- data-sanity floor ----
# Below this IV a quote is treated as degenerate (expired/stale chain),
# not "cheap premium". Contracts under it are dropped, not scored.
MIN_IV = 0.02                  # 2% — anything lower is broken data, not signal

# ---- bars used for momentum / realized vol ----
BAR_PERIOD = "5d"
BAR_INTERVAL = "15m"

# ---- output ----
EMIT_CONSOLE = True
EMIT_MARKDOWN = True
MARKDOWN_PATH = "latest_signal.md"

# ---- risk-free rate for Black-Scholes delta ----
RISK_FREE_RATE = 0.043
