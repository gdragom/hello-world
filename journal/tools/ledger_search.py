"""Shared search / report helpers for run_long.py and run_short.py."""
from __future__ import annotations

import itertools
import json
import os
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from ledger_engine import Params, backtest
from parity_tv_last365 import bull_ifvg_ok, load_csv

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUT = ROOT / "out"

# Locked per user confirm (2026-09-27)
FIXED = dict(
    bias_filter="aligned",
    entry_mode="zone_fvg_ob",
    cooldown=10,
    post_stop_cooldown=10,
    reenter=True,
    lock_fib_on_stop=False,
    min_hold_bars=0,
    be_trigger_r=0.0,
    require_body=True,
    doji_body_pct=10.0,
    atr_len=14,
    zone_keep=80,
    max_zones=12,
    use_fixed_dollar=True,
    fixed_risk_usd=500.0,
    commission_pct=0.04,
    initial_capital=10_000.0,
    rr_mult=2.0,
    sl_mode="fixed_usd",
)

SWINGS = [6, 8, 10, 12, 14, 18, 24]
ATRS = [0.45, 0.6, 0.8, 1.2]
FIBS = ["immediate", "wait"]
WICKS = [True, False]
BIAS_MODES = ["need_color", "ignore_color"]  # A/B proof
CHUNK = 40
HOLDOUT_DAYS = 90
SEARCH_DAYS = 730  # aim 2y; clipped to data
WARM_DAYS = 60


def bear_ifvg_ok(h1: pd.DataFrame, ltf: pd.DataFrame, max_age: int = 12) -> np.ndarray:
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


def resolve_h1() -> Path:
    """Prefer Bitget 1H (longer history after fetch)."""
    a = DATA / "btcusdt_1h.csv"
    b = DATA / "btcusdt_1h_bitget.csv"
    if a.exists() and b.exists():
        return b if b.stat().st_size >= a.stat().st_size else a
    if b.exists():
        return b
    return a


def resolve_ltf() -> tuple[Path, str]:
    """5m preferred for longer IFVG coverage (Pine default LTF)."""
    m5 = DATA / "btcusdt_5m_bitget.csv"
    m1 = DATA / "btcusdt_1m_bitget.csv"
    if m5.exists():
        return m5, "5m"
    return m1, "1m"


def _env_ts(name: str) -> datetime | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def window_bounds(h1: pd.DataFrame) -> dict:
    end = h1.index.max().to_pydatetime()
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    data_min = h1.index.min().to_pydatetime()
    if data_min.tzinfo is None:
        data_min = data_min.replace(tzinfo=timezone.utc)

    # Optional: LEDGER_SEARCH_FROM / LEDGER_SEARCH_TO / LEDGER_HOLDOUT_FROM
    env_search_from = _env_ts("LEDGER_SEARCH_FROM")
    env_search_to = _env_ts("LEDGER_SEARCH_TO")
    env_holdout_from = _env_ts("LEDGER_HOLDOUT_FROM")
    if env_search_from and env_search_to and env_holdout_from:
        search_from, search_to, holdout_from = env_search_from, env_search_to, env_holdout_from
    else:
        holdout_from = end - timedelta(days=HOLDOUT_DAYS)
        search_to = holdout_from
        search_from = search_to - timedelta(days=SEARCH_DAYS)

    if search_from < data_min + timedelta(days=WARM_DAYS):
        search_from = data_min + timedelta(days=WARM_DAYS)
    warm_from = search_from - timedelta(days=WARM_DAYS)
    if warm_from < data_min:
        warm_from = data_min
    return {
        "data_min": data_min,
        "warm_from": warm_from,
        "search_from": search_from,
        "search_to": search_to,
        "holdout_from": holdout_from,
        "end": end,
    }


def jobs_list():
    return list(itertools.product(SWINGS, ATRS, FIBS, WICKS, BIAS_MODES))


def make_params(side: str, swing, atr, fib, wick, bias_mode: str) -> Params:
    is_long = side == "long"
    return Params(
        swing_len=int(swing),
        min_swing_atr=float(atr),
        fib_mode=fib,  # type: ignore
        entry_mode=FIXED["entry_mode"],  # type: ignore
        bias_filter=FIXED["bias_filter"],  # type: ignore
        short_filter="long_only" if is_long else "match",  # type: ignore
        fixed_usd_sl=500.0 if is_long else 1000.0,
        fixed_tp_usd=1000.0 if is_long else 2100.0,
        fixed_risk_usd=FIXED["fixed_risk_usd"],
        zone_keep=FIXED["zone_keep"],
        max_zones=FIXED["max_zones"],
        reenter=FIXED["reenter"],
        cooldown=FIXED["cooldown"],
        post_stop_cooldown=FIXED["post_stop_cooldown"],
        lock_fib_on_stop=FIXED["lock_fib_on_stop"],
        min_hold_bars=FIXED["min_hold_bars"],
        be_trigger_r=FIXED["be_trigger_r"],
        doji_body_pct=FIXED["doji_body_pct"],
        require_body=FIXED["require_body"],
        commission_pct=FIXED["commission_pct"],
        initial_capital=FIXED["initial_capital"],
        eq_wick=bool(wick),
        use_fixed_dollar=True,
        atr_len=FIXED["atr_len"],
        rr_mult=FIXED["rr_mult"],
        sl_mode="fixed_usd",  # type: ignore
        allow_long=is_long,
        bias_sweep_mode=bias_mode,  # type: ignore
    )


def balance_score(df: pd.DataFrame, min_trades: int = 12) -> pd.Series:
    out = pd.Series(-1e9, index=df.index, dtype=float)
    ok = df["trades"] >= min_trades
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


def load_market(side: str):
    h1_path = resolve_h1()
    ltf_path, ltf_name = resolve_ltf()
    h1 = load_csv(h1_path)
    ltf = load_csv(ltf_path)
    # trim h1 to ltf overlap for IFVG validity
    overlap_start = max(h1.index.min(), ltf.index.min())
    h1 = h1.loc[h1.index >= overlap_start].copy()
    ltf = ltf.loc[ltf.index >= overlap_start].copy()
    bounds = window_bounds(h1)
    h1 = h1.loc[h1.index >= pd.Timestamp(bounds["warm_from"])].copy()
    start_search = int(
        np.searchsorted(h1.index.asi8, pd.Timestamp(bounds["search_from"]).value, side="left")
    )
    start_holdout = int(
        np.searchsorted(h1.index.asi8, pd.Timestamp(bounds["holdout_from"]).value, side="left")
    )
    if side == "long":
        ifvg = bull_ifvg_ok(h1, ltf, 12)
    else:
        ifvg = bear_ifvg_ok(h1, ltf, 12)
    return {
        "h1": h1,
        "ifvg": ifvg,
        "ltf_name": ltf_name,
        "h1_path": str(h1_path),
        "bounds": bounds,
        "start_search": start_search,
        "start_holdout": start_holdout,
    }


def run_one(side, h1, start_i, end_i, ifvg, job) -> dict:
    swing, atr, fib, wick, bias_mode = job
    p = make_params(side, swing, atr, fib, wick, bias_mode)
    # end_i exclusive: zero-out ifvg after window so no late entries; exits may still close
    ifvg_use = ifvg.copy()
    if end_i is not None and end_i < len(ifvg_use):
        ifvg_use[end_i:] = False
    m = backtest(h1, p, ifvg_ok=ifvg_use, start_i=start_i)
    return {
        "side": side,
        "swing_len": swing,
        "min_swing_atr": atr,
        "fib_mode": fib,
        "eq_wick": wick,
        "bias_sweep_mode": bias_mode,
        "bias_filter": FIXED["bias_filter"],
        "entry_mode": FIXED["entry_mode"],
        "cooldown": FIXED["cooldown"],
        "post_stop_cooldown": FIXED["post_stop_cooldown"],
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


def run_grid(side: str, resume: bool = False, tag: str = "") -> Path:
    suffix = f"_{tag}" if tag else ""
    work = Path(os.environ.get("TEMP", str(OUT))) / f"ledger_search_{side}{suffix}"
    work.mkdir(parents=True, exist_ok=True)
    log = work / "run.log"
    out_csv = work / "search_rows.csv"

    def log_msg(msg: str) -> None:
        print(msg, flush=True)
        with open(log, "a", encoding="utf-8") as f:
            f.write(datetime.now().isoformat() + " " + msg + "\n")

    mkt = load_market(side)
    h1, ifvg = mkt["h1"], mkt["ifvg"]
    start_i, hold_i = mkt["start_search"], mkt["start_holdout"]
    bounds = mkt["bounds"]
    jobs = jobs_list()
    log_msg(
        f"side={side} combos={len(jobs)} ltf={mkt['ltf_name']} h1={mkt['h1_path']}"
    )
    log_msg(
        f"search {bounds['search_from'].date()} .. {bounds['search_to'].date()} | "
        f"holdout {bounds['holdout_from'].date()} .. {bounds['end'].date()}"
    )
    if not resume and out_csv.exists():
        out_csv.unlink()

    done_n = 0
    prev = None
    if resume and out_csv.exists():
        prev = pd.read_csv(out_csv)
        done_n = len(prev)
        log_msg(f"resume from {done_n}")

    total = len(jobs)
    while done_n < total:
        end = min(done_n + CHUNK, total)
        rows = [
            run_one(side, h1, start_i, hold_i, ifvg, jobs[i]) for i in range(done_n, end)
        ]
        chunk_df = pd.DataFrame(rows)
        if prev is None:
            chunk_df.to_csv(out_csv, index=False)
            prev = chunk_df
        else:
            chunk_df.to_csv(out_csv, mode="a", header=False, index=False)
            prev = pd.concat([prev, chunk_df], ignore_index=True)
        done_n = end
        log_msg(f"[{side}] {done_n}/{total} search saved")

    df = pd.read_csv(out_csv)
    df["balance_score"] = balance_score(df)
    df = df.sort_values(["balance_score", "pf", "pnl_pct"], ascending=False).reset_index(drop=True)
    df.insert(0, "rank", np.arange(1, len(df) + 1))

    # Holdout eval for top 20
    top_n = min(20, len(df))
    hold_rows = []
    for i in range(top_n):
        r = df.iloc[i]
        job = (r.swing_len, r.min_swing_atr, r.fib_mode, bool(r.eq_wick), r.bias_sweep_mode)
        h = run_one(side, h1, hold_i, None, ifvg, job)
        h["search_rank"] = int(r["rank"])
        h["search_score"] = float(r["balance_score"])
        hold_rows.append(h)
    hold_df = pd.DataFrame(hold_rows)
    if len(hold_df):
        hold_df["balance_score"] = balance_score(hold_df, min_trades=5)
        hold_df = hold_df.sort_values(
            ["balance_score", "pf", "pnl_pct"], ascending=False
        ).reset_index(drop=True)
        hold_df.insert(0, "holdout_rank", np.arange(1, len(hold_df) + 1))

    # Mode A/B summary on search set
    mode_sum = (
        df.groupby("bias_sweep_mode")
        .agg(
            n=("trades", "count"),
            med_pf=("pf", "median"),
            med_pnl=("pnl_pct", "median"),
            med_dd=("max_dd_pct", "median"),
            med_score=("balance_score", "median"),
            best_score=("balance_score", "max"),
            mean_trades=("trades", "mean"),
        )
        .reset_index()
    )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    name = f"{side}_search_{tag}_{stamp}.xlsx" if tag else f"{side}_search_{stamp}.xlsx"
    xlsx = OUT / name
    OUT.mkdir(parents=True, exist_ok=True)
    notes = pd.DataFrame(
        [
            {"item": "side", "value": side},
            {"item": "fixed", "value": json.dumps(FIXED)},
            {"item": "sweep", "value": "swing, atr, fib, wick, bias_sweep_mode"},
            {"item": "bias_modes", "value": "need_color vs ignore_color"},
            {"item": "ltf", "value": mkt["ltf_name"]},
            {
                "item": "search",
                "value": f"{bounds['search_from'].date()} .. {bounds['search_to'].date()}",
            },
            {
                "item": "holdout",
                "value": f"{bounds['holdout_from'].date()} .. {bounds['end'].date()}",
            },
            {
                "item": "score",
                "value": "0.35*z(PF)+0.25*z(WR)+0.25*z(PnL%)-0.15*z(DD%); trades<12 penalized",
            },
            {
                "item": "data_note",
                "value": "Window clipped to OHLC∩LTF overlap; extend CSVs for full 2y",
            },
        ]
    )
    with pd.ExcelWriter(xlsx, engine="xlsxwriter") as xw:
        df.head(1).to_excel(xw, sheet_name="Search_Champ", index=False)
        hold_df.head(1).to_excel(xw, sheet_name="Holdout_Champ", index=False)
        mode_sum.to_excel(xw, sheet_name="BiasMode_Compare", index=False)
        df.head(50).to_excel(xw, sheet_name="Search_Top50", index=False)
        hold_df.to_excel(xw, sheet_name="Holdout_Top20", index=False)
        df.to_excel(xw, sheet_name="Search_All", index=False)
        notes.to_excel(xw, sheet_name="Notes", index=False)
    log_msg(f"Wrote {xlsx}")
    if len(df):
        log_msg(f"SEARCH#1 {df.iloc[0][['bias_sweep_mode','swing_len','pf','pnl_pct','max_dd_pct','balance_score']].to_dict()}")
    if len(hold_df):
        log_msg(f"HOLDOUT#1 {hold_df.iloc[0][['bias_sweep_mode','swing_len','pf','pnl_pct','max_dd_pct']].to_dict()}")
    log_msg(f"MODE\n{mode_sum.to_string(index=False)}")
    return xlsx


def run_single(side: str, **overrides) -> dict:
    mkt = load_market(side)
    job = (
        overrides.get("swing_len", 8),
        overrides.get("min_swing_atr", 0.6),
        overrides.get("fib_mode", "immediate"),
        overrides.get("eq_wick", False),
        overrides.get("bias_sweep_mode", "need_color"),
    )
    search = run_one(side, mkt["h1"], mkt["start_search"], mkt["start_holdout"], mkt["ifvg"], job)
    hold = run_one(side, mkt["h1"], mkt["start_holdout"], None, mkt["ifvg"], job)
    return {"search": search, "holdout": hold, "bounds": {k: str(v) for k, v in mkt["bounds"].items()}}
