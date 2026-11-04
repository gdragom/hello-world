#!/usr/bin/env python3
"""Compare legacy LEDGER champs vs simple ICT candidates in R units.

PnL% is not comparable across engines: legacy risks a fixed $500 per trade,
simple caps notional at 0.5x equity. R per trade (net / cash risked) is.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import ledger_search as legacy
import simple_ict as simple
from ledger_engine import backtest

OUT = Path(__file__).resolve().parent / "out"


def r_stats(r: list[float]) -> dict:
    r = [float(x) for x in r]
    if not r:
        return dict(trades=0, wr=0.0, pf_r=0.0, total_r=0.0, avg_r=0.0, max_dd_r=0.0)
    arr = np.array(r)
    cum = np.cumsum(arr)
    peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:]
    gain = arr[arr > 0].sum()
    loss = -arr[arr <= 0].sum()
    return dict(
        trades=len(arr),
        wr=round(100.0 * (arr > 0).mean(), 1),
        pf_r=round(gain / loss, 2) if loss > 0 else 99.0,
        total_r=round(arr.sum(), 2),
        avg_r=round(arr.mean(), 3),
        max_dd_r=round(float((peak - cum).max()), 2),
    )


def legacy_r(side: str, swing, atr, fib, wick, bias_mode, window: str) -> list[float]:
    mkt = legacy.load_market(side)
    p = legacy.make_params(side, swing, atr, fib, wick, bias_mode)
    ifvg = mkt["ifvg"].copy()
    if window == "search":
        start = mkt["start_search"]
        ifvg[mkt["start_holdout"]:] = False
    else:
        start = mkt["start_holdout"]
    m = backtest(mkt["h1"], p, ifvg_ok=ifvg, start_i=start, collect_trades=True)
    return [t["pnl"] / p.fixed_risk_usd for t in m.trade_log]  # type: ignore[attr-defined]


def simple_r(mkt: dict, side: str, window: str, **kw) -> list[float]:
    p = simple.SimpleParams(
        side=side,  # type: ignore
        swing_len=int(kw["swing"]),
        fib_mode=kw["fib"],
        risk_mode=kw.get("risk", "size_cap"),
        trigger=kw["trigger"],
        ltf_swing_len=int(kw.get("ltf_swing", 3)),
        ltf_sl=kw.get("ltf_sl", "leg_low"),
    )
    if window == "search":
        start, end = mkt["search_from"], mkt["search_to"]
    else:
        start, end = mkt["holdout_from"], mkt["end"]
    m = simple.backtest_simple(mkt["h1"], mkt["m5"], p, start_ts=start, end_ts=end)
    return m.r_list  # type: ignore[attr-defined]


CANDIDATES = [
    # name, family, runner
    ("Legacy LONG champ (swing12 immediate close-touch)", "legacy", "long",
     dict(swing=12, atr=0.6, fib="immediate", wick=False, bias_mode="need_color")),
    ("Legacy SHORT least-bad (swing14 immediate wick)", "legacy", "short",
     dict(swing=14, atr=0.6, fib="immediate", wick=True, bias_mode="need_color")),
    ("Simple IFVG LONG (swing8 immediate)", "simple", "long",
     dict(trigger="ifvg", swing=8, fib="immediate")),
    ("Simple MSS SHORT (swing6 wait 5m8 leg_low)", "simple", "short",
     dict(trigger="mss", swing=6, fib="wait", ltf_swing=8, ltf_sl="leg_low")),
    ("NEW both: MSS swing10 wait 5m8 leg_low", "simple", "both",
     dict(trigger="mss", swing=10, fib="wait", ltf_swing=8, ltf_sl="leg_low")),
    ("NEW both: MSS swing10 wait 5m8 pivot", "simple", "both",
     dict(trigger="mss", swing=10, fib="wait", ltf_swing=8, ltf_sl="pivot")),
    ("NEW both: IFVG swing10 wait", "simple", "both",
     dict(trigger="ifvg", swing=10, fib="wait")),
    ("NEW both: IFVG swing6 wait (search #1)", "simple", "both",
     dict(trigger="ifvg", swing=6, fib="wait")),
]


def main() -> int:
    smkt = simple.load_market()
    rows = []
    legacy_cache: dict[tuple, dict[str, list[float]]] = {}
    for name, family, side, kw in CANDIDATES:
        row = {"strategy": name, "family": family, "side": side}
        for window in ("search", "holdout"):
            if family == "legacy":
                r = legacy_r(side, kw["swing"], kw["atr"], kw["fib"], kw["wick"], kw["bias_mode"], window)
                legacy_cache.setdefault((side,), {})[window] = r
            else:
                r = simple_r(smkt, side, window, **kw)
            for k, v in r_stats(r).items():
                row[f"{window}_{k}"] = v
        rows.append(row)
        print(name, "done", flush=True)

    # Legacy has no one-book mode; sum both legacy books as a rough combined reference
    combo = {"strategy": "Legacy LONG + SHORT books (summed, separate positions)", "family": "legacy", "side": "both"}
    for window in ("search", "holdout"):
        r = legacy_cache[("long",)][window] + legacy_cache[("short",)][window]
        st = r_stats(r)
        st.pop("max_dd_r")  # order lost when concatenating two books
        for k, v in st.items():
            combo[f"{window}_{k}"] = v
        combo[f"{window}_max_dd_r"] = np.nan
    rows.insert(2, combo)

    df = pd.DataFrame(rows)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = OUT / f"compare_strategies_{stamp}.xlsx"
    notes = pd.DataFrame(
        [
            {"item": "unit", "value": "R = net trade PnL / cash risked on that trade (fees included)"},
            {"item": "why R", "value": "legacy risks fixed $500; simple caps notional 0.5x equity, so PnL% not comparable"},
            {"item": "5% rule", "value": "PnL at 5% risk per trade ~= total_r x 5% (no compounding)"},
            {"item": "search", "value": f"{smkt['search_from'].date()} .. {smkt['search_to'].date()}"},
            {"item": "holdout", "value": f"{smkt['holdout_from'].date()} .. {smkt['end'].date()}"},
        ]
    )
    with pd.ExcelWriter(path, engine="xlsxwriter") as xw:
        df.to_excel(xw, sheet_name="Compare", index=False)
        notes.to_excel(xw, sheet_name="Notes", index=False)
    pd.set_option("display.width", 250)
    cols = ["strategy"] + [f"{w}_{k}" for w in ("search", "holdout") for k in ("trades", "wr", "pf_r", "total_r", "max_dd_r")]
    print(df[cols].to_string(index=False))
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
