#!/usr/bin/env python3
"""Grid Short Fixed $ SL/TP on locked Custom pack. Rank by profit/DD balance.

Windows: last 365d and last 5y (entries). Warm-up bars kept before each window.
Uses Bitget 1H + 5m IFVG@6. Risk cash fixed at $500 on $10k capital.
"""
from __future__ import annotations

import itertools
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from ledger_engine import Params, backtest
from ledger_search import balance_score, bear_ifvg_ok
from parity_tv_last365 import load_csv

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUT = ROOT / "out"
H1 = DATA / "btcusdt_1h_bitget.csv"
M5 = DATA / "btcusdt_5m_bitget.csv"

# Locked Short structure ≈ Pine v0.9.17 Custom pack (exits vary)
PACK = dict(
    swing_len=8,
    min_swing_atr=0.6,
    atr_len=14,
    fib_mode="immediate",
    entry_mode="zone_fvg_ob",
    bias_filter="aligned",
    short_filter="match",
    cooldown=10,
    post_stop_cooldown=10,
    reenter=True,
    lock_fib_on_stop=False,
    min_hold_bars=0,
    be_trigger_r=0.0,
    require_body=True,
    doji_body_pct=10.0,
    zone_keep=80,
    max_zones=12,
    use_fixed_dollar=True,
    fixed_risk_usd=500.0,
    commission_pct=0.04,
    initial_capital=10_000.0,
    eq_wick=True,
    sl_mode="fixed_usd",
    rr_mult=2.0,
    bias_sweep_mode="need_color",
    allow_long=False,
    htf_sma_gate=True,
    htf_sma_fast=7,
    htf_sma_slow=14,
    struct_gate="any",
)

SL_GRID = [500, 750, 1000, 1250, 1500, 2000]
# Absolute TP + RR-derived vs each SL (deduped per run)
TP_ABS = [1000, 1500, 2000, 2100, 2500, 3000, 4000]
RR_GRID = [1.0, 1.5, 2.0, 2.1, 2.5, 3.0]

WINDOWS = {
    "last_365d": 365,
    "last_5y": 365 * 5,
}
WARM_DAYS = 90
IFVG_AGE = 6
MIN_TRADES = {"last_365d": 8, "last_5y": 20}


def jobs() -> list[tuple[float, float]]:
    pairs: set[tuple[float, float]] = set()
    for sl in SL_GRID:
        for tp in TP_ABS:
            pairs.add((float(sl), float(tp)))
        for rr in RR_GRID:
            pairs.add((float(sl), float(round(sl * rr, 1))))
    return sorted(pairs)


def make_p(sl: float, tp: float) -> Params:
    return Params(
        swing_len=PACK["swing_len"],
        min_swing_atr=PACK["min_swing_atr"],
        atr_len=PACK["atr_len"],
        fib_mode=PACK["fib_mode"],  # type: ignore
        entry_mode=PACK["entry_mode"],  # type: ignore
        bias_filter=PACK["bias_filter"],  # type: ignore
        short_filter=PACK["short_filter"],  # type: ignore
        fixed_usd_sl=float(sl),
        fixed_tp_usd=float(tp),
        fixed_risk_usd=PACK["fixed_risk_usd"],
        zone_keep=PACK["zone_keep"],
        max_zones=PACK["max_zones"],
        reenter=PACK["reenter"],
        cooldown=PACK["cooldown"],
        post_stop_cooldown=PACK["post_stop_cooldown"],
        lock_fib_on_stop=PACK["lock_fib_on_stop"],
        min_hold_bars=PACK["min_hold_bars"],
        be_trigger_r=PACK["be_trigger_r"],
        doji_body_pct=PACK["doji_body_pct"],
        require_body=PACK["require_body"],
        commission_pct=PACK["commission_pct"],
        initial_capital=PACK["initial_capital"],
        eq_wick=PACK["eq_wick"],
        use_fixed_dollar=True,
        rr_mult=PACK["rr_mult"],
        sl_mode="fixed_usd",  # type: ignore
        allow_long=False,
        bias_sweep_mode=PACK["bias_sweep_mode"],  # type: ignore
        htf_sma_gate=PACK["htf_sma_gate"],
        htf_sma_fast=PACK["htf_sma_fast"],
        htf_sma_slow=PACK["htf_sma_slow"],
        struct_gate=PACK["struct_gate"],  # type: ignore
    )


def run_window(
    name: str,
    days: int,
    h1: pd.DataFrame,
    ifvg: np.ndarray,
) -> pd.DataFrame:
    end = h1.index.max().to_pydatetime()
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    entry_from = end - timedelta(days=days)
    warm_from = entry_from - timedelta(days=WARM_DAYS)
    data_min = h1.index.min().to_pydatetime()
    if data_min.tzinfo is None:
        data_min = data_min.replace(tzinfo=timezone.utc)
    if warm_from < data_min:
        warm_from = data_min
    if entry_from < warm_from + timedelta(days=30):
        raise RuntimeError(f"{name}: not enough history for warm-up + window")

    mask = np.asarray(h1.index >= pd.Timestamp(warm_from))
    slice_h1 = h1.iloc[mask].copy()
    ifvg_slice = np.asarray(ifvg)[mask]
    start_i = int(slice_h1.index.searchsorted(pd.Timestamp(entry_from), side="left"))
    if start_i >= len(slice_h1):
        raise RuntimeError(
            f"{name}: entry start OOB (start_i={start_i}, bars={len(slice_h1)})"
        )
    print(
        f"  entries from {entry_from.date()} warm from {warm_from.date()} "
        f"bars={len(slice_h1)} start_i={start_i}",
        flush=True,
    )

    rows = []
    t0 = time.time()
    pair_list = jobs()
    for n, (sl, tp) in enumerate(pair_list, 1):
        p = make_p(sl, tp)
        m = backtest(slice_h1, p, start_i=start_i, ifvg_ok=ifvg_slice)
        rr = tp / sl if sl > 0 else 0.0
        rows.append(
            {
                "window": name,
                "sl": sl,
                "tp": tp,
                "rr": round(rr, 3),
                "trades": int(m.trades),
                "wins": int(m.wins),
                "wr": round(float(m.wr), 2),
                "pf": round(float(m.pf), 3),
                "pnl": round(float(m.pnl), 2),
                "pnl_pct": round(float(m.pnl_pct), 2),
                "max_dd_pct": round(float(m.max_dd_pct), 2),
                "avg_r": round(float(m.avg_r), 3),
            }
        )
        if n % 20 == 0 or n == len(pair_list):
            print(
                f"  [{name}] {n}/{len(pair_list)}  elapsed={time.time() - t0:.0f}s",
                flush=True,
            )

    df = pd.DataFrame(rows)
    min_tr = MIN_TRADES[name]
    df["balance_score"] = balance_score(df, min_trades=min_tr)
    df = df.sort_values(
        ["balance_score", "pf", "pnl_pct"], ascending=False
    ).reset_index(drop=True)
    df.insert(0, "rank", np.arange(1, len(df) + 1))
    return df


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    if not H1.exists() or not M5.exists():
        raise SystemExit(f"Missing data. Run: python3 fetch_history.py --tf 1H 5m --start 2021-01-01")

    print("Loading candles…", flush=True)
    h1 = load_csv(H1)
    m5 = load_csv(M5)
    overlap = max(h1.index.min(), m5.index.min())
    h1 = h1.loc[h1.index >= overlap].copy()
    m5 = m5.loc[m5.index >= overlap].copy()
    print(
        f"H1 {len(h1)} {h1.index.min()} .. {h1.index.max()} | "
        f"5m {len(m5)} {m5.index.min()} .. {m5.index.max()}",
        flush=True,
    )
    print(f"Building 5m bear IFVG@{IFVG_AGE}…", flush=True)
    ifvg = bear_ifvg_ok(h1, m5, IFVG_AGE)
    print(f"Combos={len(jobs())}", flush=True)

    frames = []
    for name, days in WINDOWS.items():
        print(f"=== {name} ({days}d) ===", flush=True)
        df = run_window(name, days, h1, ifvg)
        out_csv = OUT / f"short_sltp_{name}.csv"
        df.to_csv(out_csv, index=False)
        frames.append(df)
        print(f"Wrote {out_csv}", flush=True)
        top = df.head(10)
        print(top.to_string(index=False), flush=True)
        # Highlight current book + v0.9.13 book
        for label, sl, tp in [
            ("current_v0.9.17", 1000.0, 2100.0),
            ("old_v0.9.13", 1000.0, 1000.0),
            ("old_long_style", 500.0, 1100.0),
        ]:
            hit = df[(df["sl"] == sl) & (df["tp"] == tp)]
            if len(hit):
                r = hit.iloc[0]
                print(
                    f"  REF {label}: rank={int(r['rank'])} pf={r['pf']} "
                    f"pnl%={r['pnl_pct']} dd%={r['max_dd_pct']} wr={r['wr']} n={r['trades']}",
                    flush=True,
                )

    summary = pd.concat(
        [f.head(15).assign(board=f["window"].iloc[0]) for f in frames],
        ignore_index=True,
    )
    xlsx = OUT / f"short_sltp_balance_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.xlsx"
    try:
        with pd.ExcelWriter(xlsx, engine="openpyxl") as xw:
            summary.to_excel(xw, sheet_name="Top15_each", index=False)
            for f in frames:
                f.to_excel(xw, sheet_name=f["window"].iloc[0][:31], index=False)
        print(f"Excel {xlsx}", flush=True)
    except Exception as e:
        print(f"Excel skip ({e})", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
