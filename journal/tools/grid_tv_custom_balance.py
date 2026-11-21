#!/usr/bin/env python3
"""Chunked TV Custom grid -> Excel. Resume-safe. Writes after every chunk."""
from __future__ import annotations

import itertools
import os
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from ledger_engine import Params, backtest  # noqa: E402
from parity_tv_last365 import bull_ifvg_ok, load_csv  # noqa: E402

H1 = ROOT / "data" / "btcusdt_1h_bitget.csv"
M1 = ROOT / "data" / "btcusdt_1m_bitget.csv"
WORKDIR = Path(os.environ.get("TEMP", str(ROOT / "out"))) / "ledger_grid_work"
WORKDIR.mkdir(parents=True, exist_ok=True)
LOG = WORKDIR / "run.log"
STAMP = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
OUT = ROOT / "out" / f"tv_custom_grid_balance_{STAMP}.xlsx"

SWINGS = [6, 8, 10, 14]
ATRS = [0.45, 0.6, 0.8, 1.2]
FIBS = ["immediate", "wait"]
ENTRIES = ["zone_fvg_ob", "zone_only", "deep"]
BIASES = ["aligned", "block_opp", "off"]
WICKS = [True, False]
COOL, POST, REENTER = 10, 10, True
CHUNK = 40


def log(msg: str) -> None:
    print(msg, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(datetime.now().isoformat() + " " + msg + "\n")


def bear_ifvg_ok(h1, ltf, max_age=12):
    low = ltf["low"].to_numpy()
    high = ltf["high"].to_numpy()
    close = ltf["close"].to_numpy()
    n = len(ltf)
    age = np.full(n, 10_000, dtype=int)
    last_bot = np.nan
    last_inv = -10_000
    for i in range(n):
        if i >= 2 and high[i - 2] < low[i]:
            last_bot = high[i - 2]
        if not np.isnan(last_bot) and close[i] < last_bot and (i == 0 or close[i - 1] >= last_bot):
            last_inv = i
        if last_inv >= 0:
            age[i] = i - last_inv
    htf_close = h1.index + pd.Timedelta(minutes=60)
    pos = np.searchsorted(ltf.index.asi8, htf_close.asi8, side="left") - 1
    ok = np.zeros(len(h1), dtype=bool)
    valid = pos >= 0
    ok[valid] = age[pos[valid]] <= max_age
    return ok


def jobs_list():
    return list(itertools.product(SWINGS, ATRS, FIBS, ENTRIES, BIASES, WICKS))


def run_one(side, h1, start_i, ifvg, job):
    swing, atr, fib, entry, bias, wick = job
    is_long = side == "long"
    p = Params(
        swing_len=int(swing),
        min_swing_atr=float(atr),
        atr_len=14,
        fib_mode=fib,  # type: ignore
        entry_mode=entry,  # type: ignore
        bias_filter=bias,  # type: ignore
        short_filter="long_only" if is_long else "match",  # type: ignore
        rr_mult=2.0,
        sl_mode="fixed_usd",
        fixed_usd_sl=500.0 if is_long else 750.0,
        zone_keep=80,
        max_zones=12,
        reenter=REENTER,
        cooldown=COOL,
        post_stop_cooldown=POST,
        lock_fib_on_stop=False,
        min_hold_bars=0,
        be_trigger_r=0.0,
        doji_body_pct=10.0,
        require_body=True,
        commission_pct=0.04,
        initial_capital=10_000.0,
        eq_wick=bool(wick),
        use_fixed_dollar=True,
        fixed_tp_usd=1000.0 if is_long else 1500.0,
        fixed_risk_usd=500.0,
        allow_long=is_long,
    )
    m = backtest(h1, p, ifvg_ok=ifvg, start_i=start_i)
    return {
        "side": side,
        "swing_len": swing,
        "min_swing_atr": atr,
        "fib_mode": fib,
        "entry_mode": entry,
        "bias_filter": bias,
        "eq_wick": wick,
        "cooldown": COOL,
        "post_stop_cooldown": POST,
        "reenter": REENTER,
        "ifvg": "on",
        "ltf": "1m",
        "ifvg_age": 12,
        "fixed_sl": p.fixed_usd_sl,
        "fixed_tp": p.fixed_tp_usd,
        "trades": int(m.trades),
        "wins": int(m.wins),
        "wr": round(float(m.wr), 2),
        "pf": round(float(m.pf), 3),
        "pnl": round(float(m.pnl), 1),
        "pnl_pct": round(float(m.pnl_pct), 2),
        "max_dd": round(float(m.max_dd), 1),
        "max_dd_pct": round(float(m.max_dd_pct), 2),
        "avg_r": round(float(m.avg_r), 3),
    }


def balance_score(df: pd.DataFrame) -> pd.Series:
    out = pd.Series(-1e9, index=df.index, dtype=float)
    ok = df["trades"] >= 12
    if int(ok.sum()) == 0:
        return out
    sub = df.loc[ok]

    def pct(s: pd.Series) -> pd.Series:
        return s.rank(method="average", pct=True)

    out.loc[ok] = (
        0.35 * pct(sub["pf"])
        + 0.25 * pct(sub["wr"])
        + 0.25 * pct(sub["pnl_pct"])
        - 0.15 * pct(sub["max_dd_pct"])
    )
    return out


def run_side(side, h1, start_i, ifvg) -> pd.DataFrame:
    jobs = jobs_list()
    out_csv = WORKDIR / f"{side}_rows.csv"
    done_n = 0
    if out_csv.exists():
        prev = pd.read_csv(out_csv)
        done_n = len(prev)
        log(f"[{side}] resume from {done_n}")
    else:
        prev = None

    total = len(jobs)
    t0 = time.time()
    while done_n < total:
        end = min(done_n + CHUNK, total)
        chunk_rows = []
        for i in range(done_n, end):
            chunk_rows.append(run_one(side, h1, start_i, ifvg, jobs[i]))
        chunk_df = pd.DataFrame(chunk_rows)
        if prev is None:
            chunk_df.to_csv(out_csv, index=False)
            prev = chunk_df
        else:
            chunk_df.to_csv(out_csv, mode="a", header=False, index=False)
            prev = pd.concat([prev, chunk_df], ignore_index=True)
        done_n = end
        elapsed = time.time() - t0
        # rate since process start for this side call — ok enough
        rate = len(chunk_rows) / max(elapsed, 1e-6) if done_n == end and done_n <= CHUNK else done_n / max(time.time() - t0, 1e-6)
        # simpler progress
        log(f"[{side}] {done_n}/{total} saved")
        t0 = time.time()

    df = pd.read_csv(out_csv)
    df["balance_score"] = balance_score(df)
    df = df.sort_values(["balance_score", "pf", "pnl_pct"], ascending=False).reset_index(drop=True)
    df.insert(0, "rank", np.arange(1, len(df) + 1))
    return df


def main() -> int:
    try:
        resume = "--resume" in sys.argv
        days = 365
        end = datetime.now(timezone.utc)
        entry_from = end - timedelta(days=days)
        warm = entry_from - timedelta(days=60)
        log(f"Combos/side={len(jobs_list())} resume={resume} workdir={WORKDIR}")

        h1 = load_csv(H1)
        h1 = h1.loc[h1.index >= pd.Timestamp(warm)].copy()
        start_i = int(np.searchsorted(h1.index.asi8, pd.Timestamp(entry_from).value, side="left"))
        m1 = load_csv(M1)
        log("IFVG build")
        ifvg_bull = bull_ifvg_ok(h1, m1, 12)
        ifvg_bear = bear_ifvg_ok(h1, m1, 12)

        if not resume:
            for p in WORKDIR.glob("*_rows.csv"):
                p.unlink()

        long_df = run_side("long", h1, start_i, ifvg_bull)
        short_df = run_side("short", h1, start_i, ifvg_bear)

        # only write excel when both complete
        if len(long_df) < len(jobs_list()) or len(short_df) < len(jobs_list()):
            log("Incomplete — re-run with --resume")
            return 2

        notes = pd.DataFrame(
            [
                {"item": "window", "value": f"last {days}d Bitget 1H"},
                {"item": "long_book", "value": "SL$500 TP$1000 risk$500"},
                {"item": "short_book", "value": "SL$750 TP$1500 risk$500"},
                {"item": "fixed", "value": "cool10 post10 reenter True IFVG 1m/12"},
                {
                    "item": "balance_score",
                    "value": "0.35*z(PF)+0.25*z(WR)+0.25*z(PnL%)-0.15*z(DD%); trades<12 penalized",
                },
                {
                    "item": "not_in_engine",
                    "value": "structGate, Use FVG/OB toggles, needEither, zoneKeep, maxHold, exitOpp, minConf",
                },
                {"item": "confirm", "value": "Confirm top ranks on TradingView"},
            ]
        )
        champs = pd.concat(
            [
                long_df.head(1).assign(board="long_best"),
                short_df.head(1).assign(board="short_best"),
            ],
            ignore_index=True,
        )
        ROOT.joinpath("out").mkdir(parents=True, exist_ok=True)
        tmp = WORKDIR / f"out_{STAMP}.xlsx"
        with pd.ExcelWriter(tmp, engine="xlsxwriter") as xw:
            champs.to_excel(xw, sheet_name="Champions", index=False)
            long_df.head(50).to_excel(xw, sheet_name="Long_Top50", index=False)
            short_df.head(50).to_excel(xw, sheet_name="Short_Top50", index=False)
            long_df.to_excel(xw, sheet_name="Long_All", index=False)
            short_df.to_excel(xw, sheet_name="Short_All", index=False)
            notes.to_excel(xw, sheet_name="Notes", index=False)
        import shutil

        shutil.copy2(tmp, OUT)
        log(f"Wrote {OUT}")
        log(f"LONG#1 {long_df.iloc[0][['balance_score','trades','wr','pf','pnl_pct','max_dd_pct']].to_dict()}")
        log(f"SHORT#1 {short_df.iloc[0][['balance_score','trades','wr','pf','pnl_pct','max_dd_pct']].to_dict()}")
        return 0
    except Exception:
        log(traceback.format_exc())
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
