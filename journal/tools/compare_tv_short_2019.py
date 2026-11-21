#!/usr/bin/env python3
"""Long vs Short Custom pack on Bitget 2019-07-10 → now + yearly / regime slices."""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ledger_engine import Params, backtest
from parity_tv_last365 import bull_ifvg_ok, load_csv
from param_lab.serve import bear_ifvg_ok

H1 = ROOT / "data" / "btcusdt_1h_bitget.csv"
M5 = ROOT / "data" / "btcusdt_5m_bitget.csv"


def pack(*, long: bool) -> Params:
    # Same structure knobs as TV Long Custom screenshot; Short exits = Pine Short Fixed $ defaults
    return Params(
        swing_len=8,
        min_swing_atr=0.6,
        atr_len=14,
        fib_mode="immediate",
        entry_mode="zone_fvg_ob",
        bias_filter="aligned",
        short_filter="long_only" if long else "match",
        rr_mult=2.0,
        sl_mode="fixed_usd",
        fixed_usd_sl=500.0 if long else 750.0,
        zone_keep=60,
        max_zones=12,
        reenter=True,
        cooldown=10,
        post_stop_cooldown=10,
        lock_fib_on_stop=False,
        min_hold_bars=0,
        be_trigger_r=0.0,
        doji_body_pct=10.0,
        require_body=True,
        commission_pct=0.04,
        initial_capital=10_000.0,
        eq_wick=True,
        use_fixed_dollar=True,
        fixed_tp_usd=1000.0 if long else 1500.0,
        fixed_risk_usd=500.0,
        allow_long=long,
    )


def fmt(m, label: str) -> None:
    print(
        f"{label:8s} n={m.trades:3d} WR={m.wr:5.1f}% PF={m.pf:5.3f} "
        f"PnL={m.pnl:9.1f} ({m.pnl_pct:6.1f}%) DD={m.max_dd_pct:5.1f}%",
        flush=True,
    )


def yearly(trades: list, h1: pd.DataFrame) -> None:
    by = defaultdict(lambda: {"n": 0, "wins": 0, "pnl": 0.0})
    for t in trades:
        y = str(t["entry_time"])[:4]
        by[y]["n"] += 1
        by[y]["pnl"] += t["pnl"]
        if t["pnl"] > 0:
            by[y]["wins"] += 1
    print("\nShort by calendar year (entry year)", flush=True)
    print(f"{'year':6s} {'n':>4s} {'WR%':>6s} {'PnL$':>10s} {'BTC%':>8s}", flush=True)
    close = h1["close"]
    for y in sorted(by):
        r = by[y]
        wr = 100.0 * r["wins"] / r["n"] if r["n"] else 0.0
        # BTC path that year
        mask = (h1.index.year == int(y))
        c = close.loc[mask]
        btc = (c.iloc[-1] / c.iloc[0] - 1.0) * 100.0 if len(c) > 1 else float("nan")
        print(f"{y:6s} {r['n']:4d} {wr:6.1f} {r['pnl']:10.1f} {btc:7.1f}%", flush=True)


def bull_bear_split(trades: list, h1: pd.DataFrame) -> None:
    """Split short trades by whether prior 90d BTC return was up (bull) or down (bear)."""
    close = h1["close"]
    buckets = {
        "bull_90d": {"n": 0, "wins": 0, "pnl": 0.0},
        "bear_90d": {"n": 0, "wins": 0, "pnl": 0.0},
    }
    for t in trades:
        ts = pd.Timestamp(t["entry_time"])
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        end = close.index.searchsorted(ts, side="right") - 1
        if end < 90 * 24:
            continue
        c0 = float(close.iloc[end - 90 * 24])
        c1 = float(close.iloc[end])
        key = "bull_90d" if c1 >= c0 else "bear_90d"
        buckets[key]["n"] += 1
        buckets[key]["pnl"] += t["pnl"]
        if t["pnl"] > 0:
            buckets[key]["wins"] += 1
    print("\nShort by prior 90d BTC regime", flush=True)
    for k, r in buckets.items():
        wr = 100.0 * r["wins"] / r["n"] if r["n"] else 0.0
        print(f"  {k:10s} n={r['n']:3d} WR={wr:5.1f}% PnL={r['pnl']:9.1f}", flush=True)


def main() -> int:
    h1 = load_csv(H1)
    m5 = load_csv(M5)
    print(f"H1 {len(h1)} {h1.index.min()} .. {h1.index.max()}", flush=True)
    print(f"M5 {len(m5)} {m5.index.min()} .. {m5.index.max()}", flush=True)
    print(
        "Pack: sw8 a0.6 immediate zone_fvg_ob aligned wick c10/10 "
        "ifvg5m@6 zoneKeep60 | Long SL500/TP1000 | Short SL750/TP1500",
        flush=True,
    )

    bull = bull_ifvg_ok(h1, m5, 6)
    bear = bear_ifvg_ok(h1, m5, 6)

    m_long = backtest(h1, pack(long=True), ifvg_ok=bull, start_i=0, collect_trades=True)
    m_short = backtest(h1, pack(long=False), ifvg_ok=bear, start_i=0, collect_trades=True)

    print("---", flush=True)
    fmt(m_long, "LONG")
    fmt(m_short, "SHORT")
    print(
        f"BTC path {float(h1['close'].iloc[0]):.0f} -> {float(h1['close'].iloc[-1]):.0f} "
        f"({(float(h1['close'].iloc[-1]) / float(h1['close'].iloc[0]) - 1) * 100:.0f}%)",
        flush=True,
    )

    trades = getattr(m_short, "trade_log", [])
    yearly(trades, h1)
    bull_bear_split(trades, h1)

    stops = sum(1 for t in trades if t.get("is_stop"))
    print(
        f"\nShort exits: stops={stops}/{len(trades)} "
        f"({100.0 * stops / len(trades) if trades else 0:.0f}% hit SL)",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
