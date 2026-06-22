"""Entrypoint. Run: python screener.py

Pulls IWM/QQQ/SPY, scores each on five factors, picks one strike per ETF,
ranks the three, and emits console + markdown.

yfinance data is delayed — this is a pre-market / open SETUP tool, not a
live intraday trigger. Treat the output as "here's the bias and the strike
to watch today," then confirm on the live tape before entering.
"""
from __future__ import annotations

import datetime as dt
import sys

import config as C
from data_providers import get_provider
from scoring import analyze_underlying, pick_contract, build_signal, _dte


def run():
    provider = get_provider(C.PROVIDER)

    # pass 1: underlyings (needed for relative strength across the cohort)
    unders = {}
    for sym in C.TICKERS:
        try:
            bars = provider.get_intraday_bars(sym, C.BAR_PERIOD, C.BAR_INTERVAL)
            unders[sym] = analyze_underlying(sym, bars)
        except Exception as e:
            print(f"[warn] {sym}: underlying fetch failed: {e}", file=sys.stderr)

    if not unders:
        print("No underlyings could be analyzed. Aborting.", file=sys.stderr)
        sys.exit(1)

    all_momos = [u.momentum for u in unders.values()]

    # pass 2: pick expiry in DTE window, choose strike, score
    signals = []
    for sym, u in unders.items():
        try:
            expiries = provider.get_expiries(sym)
        except Exception as e:
            print(f"[warn] {sym}: expiry fetch failed: {e}", file=sys.stderr)
            continue

        valid = [e for e in expiries if C.MIN_DTE <= _dte(e) <= C.MAX_DTE]
        if not valid:
            print(f"[warn] {sym}: no expiry in {C.MIN_DTE}-{C.MAX_DTE} DTE window",
                  file=sys.stderr)
            continue
        expiry = valid[0]  # nearest qualifying

        try:
            chain = provider.get_chain(sym, expiry)
        except Exception as e:
            print(f"[warn] {sym}: chain fetch failed: {e}", file=sys.stderr)
            continue

        contract = pick_contract(u, chain, expiry)
        if contract is None:
            side = "call" if u.bias >= 0 else "put"
            print(f"[warn] {sym}: no valid contract on {side} side", file=sys.stderr)
            continue

        signals.append(build_signal(u, contract, expiry, all_momos))

    if not signals:
        msg = ("No tradeable chains right now. This usually means the run "
               "happened outside market hours or on a chain at/after expiry "
               "(IV collapsed, deltas pinned). Re-run during the session.")
        print(msg, file=sys.stderr)
        if C.EMIT_MARKDOWN:
            import datetime as _dt
            with open(C.MARKDOWN_PATH, "w") as f:
                f.write(f"# 0-2 DTE Index ETF Signal — "
                        f"{_dt.datetime.now():%Y-%m-%d %H:%M}\n\n_{msg}_\n")
        return  # clean exit — not a failure

    signals.sort(key=lambda s: s.composite, reverse=True)

    if C.EMIT_CONSOLE:
        _print_console(signals)
    if C.EMIT_MARKDOWN:
        _write_markdown(signals)


def _fmt_strike(s):
    c = s.contract
    return f"{s.symbol} {c.expiry} {c.strike:g}{'C' if s.side == 'call' else 'P'}"


def _print_console(signals):
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"\n=== 0-2 DTE INDEX ETF SCREENER  ({now}) ===")
    print("Pre-market/open setup tool. Delayed data — confirm on live tape.\n")
    for rank, s in enumerate(signals, 1):
        c = s.contract
        flag = "" if s.liquid_ok else "  [!] thin liquidity"
        print(f"#{rank}  {_fmt_strike(s)}   score {s.composite:.3f}{flag}")
        print(f"      spot {s.spot:.2f}  bias {s.side.upper()}  "
              f"delta {c.delta:+.2f}  IV {c.iv*100:.1f}%")
        print(f"      mid {c.mid:.2f}  spread {c.spread_pct:.1f}%  "
              f"OI {c.open_interest}  vol {c.volume}")
        fa = "  ".join(f"{k.split('_')[0]}:{v:.2f}" for k, v in s.factors.items())
        print(f"      {fa}\n")


def _write_markdown(signals):
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"# 0-2 DTE Index ETF Signal — {now}",
        "",
        "_Pre-market/open setup tool. yfinance data is delayed — confirm on the "
        "live tape before entering. Not trade advice._",
        "",
        "| Rank | Contract | Side | Score | Spot | Δ | IV | Mid | Spread | OI | Vol | Liquid |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for rank, s in enumerate(signals, 1):
        c = s.contract
        lines.append(
            f"| {rank} | {_fmt_strike(s)} | {s.side.upper()} | {s.composite:.3f} | "
            f"{s.spot:.2f} | {c.delta:+.2f} | {c.iv*100:.1f}% | {c.mid:.2f} | "
            f"{c.spread_pct:.1f}% | {c.open_interest} | {c.volume} | "
            f"{'yes' if s.liquid_ok else 'NO'} |"
        )
    lines += ["", "## Factor breakdown", ""]
    for rank, s in enumerate(signals, 1):
        fa = ", ".join(f"{k}: {v:.2f}" for k, v in s.factors.items())
        lines.append(f"{rank}. **{_fmt_strike(s)}** — {fa}")

    with open(C.MARKDOWN_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[ok] wrote {C.MARKDOWN_PATH}")


if __name__ == "__main__":
    run()
