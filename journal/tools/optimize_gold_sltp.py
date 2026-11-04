#!/usr/bin/env python3
"""Grid fixed $ SL/TP for LEDGER Gold Custom pack (5m IFVG). Rank by balance_score."""
from __future__ import annotations

import itertools
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from ledger_engine import Params, backtest
from ledger_search import balance_score, bear_ifvg_ok
from parity_tv_last365 import bull_ifvg_ok, load_csv

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUT = ROOT / "out"

# User Custom pack (locked) — only SL/TP vary
PACK = dict(
    swing_len=8,
    min_swing_atr=0.6,
    atr_len=14,
    fib_mode="immediate",
    entry_mode="zone_fvg_ob",
    bias_filter="aligned",
    cooldown=10,
    post_stop_cooldown=10,
    reenter=True,
    lock_fib_on_stop=False,
    min_hold_bars=0,
    be_trigger_r=0.0,
    require_body=True,
    doji_body_pct=10.0,
    zone_keep=60,
    max_zones=12,
    use_fixed_dollar=True,
    fixed_risk_usd=500.0,
    commission_pct=0.04,
    initial_capital=10_000.0,
    eq_wick=True,
    sl_mode="fixed_usd",
    rr_mult=2.0,
    bias_sweep_mode="need_color",
)

# Gold price-scale grid (USD point distances)
SL_LONG = [15, 20, 25, 30, 35, 40, 50, 60, 80, 100]
SL_SHORT = [20, 30, 40, 50, 60, 80, 100, 120, 150]
RR = [1.5, 2.0, 2.5, 3.0]

HOLDOUT_DAYS = 90
SEARCH_DAYS = 730
WARM_DAYS = 60
MIN_TRADES_SEARCH = 8
MIN_TRADES_HOLD = 3


def make_p(side: str, sl: float, tp: float) -> Params:
    is_long = side == "long"
    return Params(
        swing_len=PACK["swing_len"],
        min_swing_atr=PACK["min_swing_atr"],
        atr_len=PACK["atr_len"],
        fib_mode=PACK["fib_mode"],  # type: ignore
        entry_mode=PACK["entry_mode"],  # type: ignore
        bias_filter=PACK["bias_filter"],  # type: ignore
        short_filter="long_only" if is_long else "match",  # type: ignore
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
        allow_long=is_long,
        bias_sweep_mode=PACK["bias_sweep_mode"],  # type: ignore
    )


def load_gold(side: str):
    h1 = load_csv(DATA / "xauusdt_1h_bitget.csv")
    ltf = load_csv(DATA / "xauusdt_5m_bitget.csv")
    overlap = max(h1.index.min(), ltf.index.min())
    h1 = h1.loc[h1.index >= overlap].copy()
    ltf = ltf.loc[ltf.index >= overlap].copy()

    end = h1.index.max().to_pydatetime()
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    data_min = h1.index.min().to_pydatetime()
    if data_min.tzinfo is None:
        data_min = data_min.replace(tzinfo=timezone.utc)

    holdout_from = end - timedelta(days=HOLDOUT_DAYS)
    search_to = holdout_from
    search_from = search_to - timedelta(days=SEARCH_DAYS)
    if search_from < data_min + timedelta(days=WARM_DAYS):
        search_from = data_min + timedelta(days=WARM_DAYS)
    warm_from = max(data_min, search_from - timedelta(days=WARM_DAYS))

    h1 = h1.loc[h1.index >= pd.Timestamp(warm_from)].copy()
    start_search = int(
        np.searchsorted(h1.index.asi8, pd.Timestamp(search_from).value, side="left")
    )
    start_hold = int(
        np.searchsorted(h1.index.asi8, pd.Timestamp(holdout_from).value, side="left")
    )
    ifvg = bull_ifvg_ok(h1, ltf, 12) if side == "long" else bear_ifvg_ok(h1, ltf, 12)
    return {
        "h1": h1,
        "ifvg": ifvg,
        "start_search": start_search,
        "start_hold": start_hold,
        "search_from": search_from,
        "holdout_from": holdout_from,
        "end": end,
    }


def run_side(side: str) -> pd.DataFrame:
    mkt = load_gold(side)
    h1, ifvg = mkt["h1"], mkt["ifvg"]
    sls = SL_LONG if side == "long" else SL_SHORT
    rows = []
    jobs = list(itertools.product(sls, RR))
    print(
        f"{side}: {len(jobs)} SL/TP combos | search {mkt['search_from'].date()} -> "
        f"{mkt['holdout_from'].date()} | holdout -> {mkt['end'].date()}",
        flush=True,
    )

    for i, (sl, rr) in enumerate(jobs, 1):
        tp = round(sl * rr, 2)
        p = make_p(side, sl, tp)
        ifvg_s = ifvg.copy()
        ifvg_s[mkt["start_hold"] :] = False
        ms = backtest(h1, p, ifvg_ok=ifvg_s, start_i=mkt["start_search"])

        ifvg_h = ifvg.copy()
        ifvg_h[: mkt["start_hold"]] = False
        mh = backtest(h1, p, ifvg_ok=ifvg_h, start_i=mkt["start_hold"])

        rows.append(
            {
                "side": side,
                "sl": sl,
                "tp": tp,
                "rr": rr,
                "trades": int(ms.trades),
                "wr": round(float(ms.wr), 2),
                "pf": round(float(ms.pf), 3),
                "pnl_pct": round(float(ms.pnl_pct), 2),
                "max_dd_pct": round(float(ms.max_dd_pct), 2),
                "avg_r": round(float(ms.avg_r), 3),
                "hold_trades": int(mh.trades),
                "hold_wr": round(float(mh.wr), 2),
                "hold_pf": round(float(mh.pf), 3),
                "hold_pnl_pct": round(float(mh.pnl_pct), 2),
                "hold_max_dd_pct": round(float(mh.max_dd_pct), 2),
            }
        )
        if i % 10 == 0 or i == len(jobs):
            print(f"  {side} {i}/{len(jobs)}", flush=True)

    df = pd.DataFrame(rows)
    df["balance_score"] = balance_score(df, min_trades=MIN_TRADES_SEARCH)
    # Holdout bonus if enough trades
    hold_ok = df["hold_trades"] >= MIN_TRADES_HOLD
    hold_bonus = pd.Series(0.0, index=df.index)
    if int(hold_ok.sum()) > 0:
        sub = df.loc[hold_ok]
        hold_bonus.loc[hold_ok] = (
            0.4 * sub["hold_pf"].rank(pct=True)
            + 0.3 * sub["hold_wr"].rank(pct=True)
            + 0.3 * sub["hold_pnl_pct"].rank(pct=True)
            - 0.2 * sub["hold_max_dd_pct"].rank(pct=True)
        )
    df["combined_score"] = df["balance_score"] + 0.35 * hold_bonus
    df = df.sort_values(
        ["combined_score", "balance_score", "pf", "pnl_pct"], ascending=False
    ).reset_index(drop=True)
    return df


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    frames = []
    for side in ("long", "short"):
        df = run_side(side)
        frames.append(df)
        path = OUT / f"gold_{side}_sltp_{stamp}.csv"
        df.to_csv(path, index=False)
        print(f"\n=== {side.upper()} TOP 8 (combined_score) ===", flush=True)
        cols = [
            "sl",
            "tp",
            "rr",
            "trades",
            "wr",
            "pf",
            "pnl_pct",
            "max_dd_pct",
            "hold_trades",
            "hold_pf",
            "hold_pnl_pct",
            "balance_score",
            "combined_score",
        ]
        print(df[cols].head(8).to_string(index=False), flush=True)
        best = df.iloc[0]
        print(
            f"BEST {side}: SL=${best.sl} TP=${best.tp} (RR {best.rr}) "
            f"search n={best.trades} WR={best.wr}% PF={best.pf} PnL%={best.pnl_pct} "
            f"DD%={best.max_dd_pct} | hold n={best.hold_trades} PF={best.hold_pf}",
            flush=True,
        )

    both = pd.concat(frames, ignore_index=True)
    xlsx = OUT / f"gold_sltp_{stamp}.xlsx"
    with pd.ExcelWriter(xlsx, engine="openpyxl") as w:
        for side, df in zip(("long", "short"), frames):
            df.to_excel(w, sheet_name=side, index=False)
        both.to_excel(w, sheet_name="all", index=False)
    print(f"\nWrote {xlsx}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
