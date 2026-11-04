"""
Simple ICT restart — mirrors user logic (Long; Short = mirror).

1. Daily bias need_color → aligned only
2. 1H swings / BOS → Fib + FVG + OB
3. Only FVG/OB in discount (long) / premium (short) vs Fib 0.5
4. Trigger on 5m:
   - ifvg: enter at 5m close on the bar IFVG goes live (invasion); SL = Fib extreme
   - mss:  price taps 1H zone (arms), then 5m MSS (bearish 5m structure broken
           back up by close above last 5m swing high); SL = previous 5m swing low
5. TP = 2R; risk_mode size_cap | skip_if_far (5% equity / 5% price)
"""
from __future__ import annotations

import itertools
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

from ledger_engine import Metrics, _atr, _daily_bias, _pivots
from parity_tv_last365 import load_csv

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUT = ROOT / "out"

FibMode = Literal["immediate", "wait"]
RiskMode = Literal["size_cap", "skip_if_far"]
Trigger = Literal["ifvg", "mss"]
# leg_low = lowest 5m low of the down leg that MSS breaks (no pivot lag)
# pivot   = last confirmed 5m pivot low (lags ltf_swing_len bars)
LtfSl = Literal["leg_low", "pivot"]

SWINGS = [6, 8, 10, 12, 14, 18, 24]
FIB_MODES: list[FibMode] = ["immediate", "wait"]
RISK_MODES: list[RiskMode] = ["size_cap", "skip_if_far"]
LTF_SWINGS = [2, 3, 5, 8]
LTF_SLS: list[LtfSl] = ["leg_low", "pivot"]
ARM_MAX_BARS = 48  # 5m bars (4h) a zone tap stays armed waiting for MSS
MIN_SWING_ATR = 0.6
IFVG_MAX_AGE = 0  # only the live invasion bar
MAX_RISK_FRAC = 0.05
RR = 2.0
COMMISSION = 0.04
CAPITAL = 10_000.0
ZONE_KEEP = 80
MAX_ZONES = 12
FIB_MAX_BARS = 60
HOLDOUT_DAYS = 90
SEARCH_DAYS = 730
WARM_DAYS = 60
CHUNK = 14


@dataclass(frozen=True)
class SimpleParams:
    # both = one book; daily bias picks direction (bull: long only, bear: short only)
    side: Literal["long", "short", "both"] = "long"
    swing_len: int = 12
    min_swing_atr: float = MIN_SWING_ATR
    fib_mode: FibMode = "immediate"
    risk_mode: RiskMode = "size_cap"
    atr_len: int = 14
    require_body: bool = True
    doji_body_pct: float = 10.0
    initial_capital: float = CAPITAL
    commission_pct: float = COMMISSION
    rr_mult: float = RR
    max_risk_frac: float = MAX_RISK_FRAC
    trigger: Trigger = "ifvg"
    ltf_swing_len: int = 3
    ltf_sl: LtfSl = "leg_low"
    arm_max_bars: int = ARM_MAX_BARS


def _ifvg_events(ltf: pd.DataFrame, *, bull: bool) -> np.ndarray:
    """True on LTF bars where IFVG invasion completes (goes live)."""
    low = ltf["low"].to_numpy()
    high = ltf["high"].to_numpy()
    close = ltf["close"].to_numpy()
    n = len(ltf)
    ev = np.zeros(n, dtype=bool)
    last_level = np.nan
    for i in range(n):
        if bull:
            # bearish FVG then close above its top
            if i >= 2 and low[i - 2] > high[i]:
                last_level = low[i - 2]
            if not np.isnan(last_level) and close[i] > last_level and (i == 0 or close[i - 1] <= last_level):
                ev[i] = True
        else:
            # bullish FVG then close below its bottom
            if i >= 2 and high[i - 2] < low[i]:
                last_level = high[i - 2]
            if not np.isnan(last_level) and close[i] < last_level and (i == 0 or close[i - 1] >= last_level):
                ev[i] = True
    return ev


def _hit_zone(zones, lo, hi, eq, fib_lo, fib_hi, is_long: bool, *, is_fvg: bool) -> bool:
    for z in zones:
        if not z[3]:
            continue
        t, b = z[0], z[1]
        if is_long:
            if is_fvg:
                ok_band = b < eq and t > fib_lo
            else:
                ok_band = b >= fib_lo and t <= eq
            if ok_band and lo <= t and hi >= b:
                return True
        else:
            if is_fvg:
                ok_band = t > eq and b < fib_hi
            else:
                ok_band = b >= eq and t <= fib_hi
            if ok_band and hi >= b and lo <= t:
                return True
    return False


def backtest_simple(
    h1: pd.DataFrame,
    m5: pd.DataFrame,
    p: SimpleParams,
    start_ts: pd.Timestamp | None = None,
    end_ts: pd.Timestamp | None = None,
) -> Metrics:
    """5m-driven entries; 1H structure updates on each completed 1H bar."""
    o = h1["open"].to_numpy(float)
    h = h1["high"].to_numpy(float)
    l = h1["low"].to_numpy(float)
    c = h1["close"].to_numpy(float)
    n = len(h1)
    if n < p.swing_len * 3 + 50:
        return Metrics()

    atr = _atr(h, l, c, p.atr_len)
    ph_raw, pl_raw = _pivots(h, l, p.swing_len, p.swing_len)
    bias = _daily_bias(h1, p.doji_body_pct, "need_color")

    m5h = m5["high"].to_numpy(float)
    m5l = m5["low"].to_numpy(float)
    m5c = m5["close"].to_numpy(float)
    m5_idx = m5.index
    n5 = len(m5)
    allow_long = p.side in ("long", "both")
    allow_short = p.side in ("short", "both")
    use_mss = p.trigger == "mss"
    no_ev = np.zeros(n5, dtype=bool)
    if use_mss:
        ph5, pl5 = _pivots(m5h, m5l, p.ltf_swing_len, p.ltf_swing_len)
        bull_ifvg = bear_ifvg = no_ev
    else:
        ph5 = pl5 = None
        bull_ifvg = _ifvg_events(m5, bull=True) if allow_long else no_ev
        bear_ifvg = _ifvg_events(m5, bull=False) if allow_short else no_ev

    # 1H bar close time = open + 1h
    h1_close_asi8 = (h1.index + pd.Timedelta(hours=1)).asi8
    m5_asi8 = m5_idx.asi8

    last_sh = np.nan
    last_sl = np.nan
    b_bos = False
    b_bos_bar = -1
    b_level = np.nan
    b_prior_sl = np.nan
    b_fib_on = False
    b_fib_hi = b_fib_lo = b_eq = np.nan
    b_fib_bar = -1
    b_entered = False
    s_bos = False
    s_bos_bar = -1
    s_level = np.nan
    s_prior_sh = np.nan
    s_fib_on = False
    s_fib_hi = s_fib_lo = s_eq = np.nan
    s_fib_bar = -1
    s_entered = False
    bf: list = []
    sf: list = []
    bo: list = []
    so: list = []

    equity = p.initial_capital
    peak = equity
    max_dd = 0.0
    max_dd_pct = 0.0
    pnl_list: list[float] = []
    r_list: list[float] = []
    side_pnl: dict[int, list[float]] = {1: [], -1: []}

    pos = 0
    entry_px = sl = tp = qty = 0.0
    risk_cash = 0.0

    def push_zone(zones, top, bot, bar):
        zones.append([top, bot, bar, True])
        if len(zones) > MAX_ZONES:
            zones.pop(0)

    def maintain(zones, is_bull_z, i_h1, close_px):
        for z in zones:
            if not z[3]:
                continue
            age = i_h1 - z[2]
            kill = age > ZONE_KEEP
            if is_bull_z and close_px < z[1]:
                kill = True
            if (not is_bull_z) and close_px > z[0]:
                kill = True
            if kill:
                z[3] = False

    def close_pos(px: float, is_stop: bool):
        nonlocal pos, equity, peak, max_dd, max_dd_pct, b_entered, s_entered
        if pos == 0:
            return
        gross = (px - entry_px) * qty * pos
        fee = (abs(entry_px) + abs(px)) * qty * (p.commission_pct / 100.0)
        net = gross - fee
        equity += net
        pnl_list.append(net)
        side_pnl[pos].append(net)
        if risk_cash > 0:
            r_list.append(net / risk_cash)
        peak = max(peak, equity)
        dd = peak - equity
        max_dd = max(max_dd, dd)
        max_dd_pct = max(max_dd_pct, dd / peak * 100.0 if peak > 0 else 0.0)
        if pos > 0:
            b_entered = True
        else:
            s_entered = True
        pos = 0

    def update_h1(i: int):
        nonlocal last_sh, last_sl
        nonlocal b_bos, b_bos_bar, b_level, b_prior_sl, b_fib_on, b_fib_hi, b_fib_lo, b_eq, b_fib_bar, b_entered
        nonlocal s_bos, s_bos_bar, s_level, s_prior_sh, s_fib_on, s_fib_hi, s_fib_lo, s_eq, s_fib_bar, s_entered
        a = atr[i]
        if np.isnan(a):
            return
        min_dist = 0.0 if p.min_swing_atr <= 0 else a * p.min_swing_atr
        if not np.isnan(ph_raw[i]):
            if min_dist <= 0 or np.isnan(last_sl) or (ph_raw[i] - last_sl) >= min_dist:
                last_sh = ph_raw[i]
        if not np.isnan(pl_raw[i]):
            if min_dist <= 0 or np.isnan(last_sh) or (last_sh - pl_raw[i]) >= min_dist:
                last_sl = pl_raw[i]

        body_top = max(o[i], c[i])
        body_bot = min(o[i], c[i])

        if i >= 2:
            if h[i - 2] < l[i] and l[i] > h[i - 2]:
                push_zone(bf, l[i], h[i - 2], i)
            if l[i - 2] > h[i]:
                push_zone(sf, l[i - 2], h[i], i)
        if i >= 1:
            if c[i - 1] < o[i - 1] and c[i] > h[i - 1]:
                push_zone(bo, o[i - 1], c[i - 1], i - 1)
            if c[i - 1] > o[i - 1] and c[i] < l[i - 1]:
                push_zone(so, c[i - 1], o[i - 1], i - 1)

        if b_fib_on and (i - b_fib_bar > FIB_MAX_BARS or c[i] < b_fib_lo):
            b_fib_on = False
            b_entered = False
        if s_fib_on and (i - s_fib_bar > FIB_MAX_BARS or c[i] > s_fib_hi):
            s_fib_on = False
            s_entered = False
        if b_bos and not b_fib_on and not np.isnan(b_level) and c[i] < b_level:
            b_bos = False
        if s_bos and not s_fib_on and not np.isnan(s_level) and c[i] > s_level:
            s_bos = False

        bull_break = (not np.isnan(last_sh)) and c[i] > last_sh and (
            (not p.require_body) or body_top > last_sh
        )
        if bull_break and not b_bos and not b_fib_on:
            s_bos = s_fib_on = False
            s_entered = False
            b_bos = True
            b_bos_bar = i
            b_level = last_sh
            b_prior_sl = last_sl
            b_entered = False
            if p.fib_mode == "immediate":
                fib_hi = max(h[i], b_level)
                fib_lo = b_prior_sl if not np.isnan(b_prior_sl) else last_sl
                if not np.isnan(fib_lo) and fib_hi > fib_lo:
                    b_fib_hi, b_fib_lo = fib_hi, fib_lo
                    b_eq = b_fib_lo + (b_fib_hi - b_fib_lo) * 0.5
                    b_fib_on = True
                    b_fib_bar = i
                    b_bos = False

        if b_bos and not b_fib_on and not np.isnan(ph_raw[i]):
            sh_bar = i - p.swing_len
            if sh_bar > b_bos_bar:
                fib_lo = last_sl if not np.isnan(last_sl) else b_prior_sl
                if not np.isnan(fib_lo) and ph_raw[i] > fib_lo:
                    b_fib_hi, b_fib_lo = ph_raw[i], fib_lo
                    b_eq = b_fib_lo + (b_fib_hi - b_fib_lo) * 0.5
                    b_fib_on = True
                    b_fib_bar = i
                    b_bos = False
                    b_entered = False

        if (
            b_fib_on
            and p.fib_mode == "immediate"
            and not np.isnan(ph_raw[i])
            and (i - p.swing_len) > b_fib_bar
            and ph_raw[i] > b_fib_hi
            and ph_raw[i] > b_fib_lo
        ):
            b_fib_hi = ph_raw[i]
            b_eq = b_fib_lo + (b_fib_hi - b_fib_lo) * 0.5

        bear_break = (not np.isnan(last_sl)) and c[i] < last_sl and (
            (not p.require_body) or body_bot < last_sl
        )
        if bear_break and not s_bos and not s_fib_on:
            b_bos = b_fib_on = False
            b_entered = False
            s_bos = True
            s_bos_bar = i
            s_level = last_sl
            s_prior_sh = last_sh
            s_entered = False
            if p.fib_mode == "immediate":
                fib_lo = min(l[i], s_level)
                fib_hi = s_prior_sh if not np.isnan(s_prior_sh) else last_sh
                if not np.isnan(fib_hi) and fib_hi > fib_lo:
                    s_fib_hi, s_fib_lo = fib_hi, fib_lo
                    s_eq = s_fib_hi - (s_fib_hi - s_fib_lo) * 0.5
                    s_fib_on = True
                    s_fib_bar = i
                    s_bos = False

        if s_bos and not s_fib_on and not np.isnan(pl_raw[i]):
            sl_bar = i - p.swing_len
            if sl_bar > s_bos_bar:
                fib_hi = last_sh if not np.isnan(last_sh) else s_prior_sh
                if not np.isnan(fib_hi) and fib_hi > pl_raw[i]:
                    s_fib_hi, s_fib_lo = fib_hi, pl_raw[i]
                    s_eq = s_fib_hi - (s_fib_hi - s_fib_lo) * 0.5
                    s_fib_on = True
                    s_fib_bar = i
                    s_bos = False
                    s_entered = False

        maintain(bf, True, i, c[i])
        maintain(sf, False, i, c[i])
        maintain(bo, True, i, c[i])
        maintain(so, False, i, c[i])

    def open_pos(side: int, px: float, stop: float) -> bool:
        nonlocal pos, entry_px, sl, tp, qty, risk_cash, b_entered, s_entered
        risk = (px - stop) * side
        if risk <= 0:
            return False
        if p.risk_mode == "skip_if_far" and (risk / px) > p.max_risk_frac:
            return False
        rc = equity * p.max_risk_frac
        q = min(rc / risk, equity * 0.5 / px)
        if q <= 0:
            return False
        pos = side
        entry_px = px
        sl = stop
        tp = px + side * risk * p.rr_mult
        qty = q
        risk_cash = q * risk
        if side > 0:
            b_entered = True
        else:
            s_entered = True
        return True

    def long_zone_tap(lo: float, hi: float) -> bool:
        if not (lo <= b_eq and hi >= b_fib_lo):
            return False
        return _hit_zone(bf, lo, hi, b_eq, b_fib_lo, b_fib_hi, True, is_fvg=True) or _hit_zone(
            bo, lo, hi, b_eq, b_fib_lo, b_fib_hi, True, is_fvg=False
        )

    def short_zone_tap(lo: float, hi: float) -> bool:
        if not (hi >= s_eq and lo <= s_fib_hi):
            return False
        return _hit_zone(sf, lo, hi, s_eq, s_fib_lo, s_fib_hi, False, is_fvg=True) or _hit_zone(
            so, lo, hi, s_eq, s_fib_lo, s_fib_hi, False, is_fvg=False
        )

    # 5m structure (mss trigger only): state5 = direction of last 5m break
    lsh5 = lsl5 = np.nan
    state5 = 0
    leg_lo = np.nan  # lowest low since 5m turned bearish (long stop)
    leg_hi = np.nan  # highest high since 5m turned bullish (short stop)
    arm_j = {1: -(10**9), -1: -(10**9)}
    arm_fib = {1: -1, -1: -1}

    h1_i = -1
    start_asi8 = pd.Timestamp(start_ts).value if start_ts is not None else None
    end_asi8 = pd.Timestamp(end_ts).value if end_ts is not None else None

    for j in range(n5):
        # advance all 1H bars whose close <= this 5m open time
        while h1_i + 1 < n and h1_close_asi8[h1_i + 1] <= m5_asi8[j]:
            h1_i += 1
            update_h1(h1_i)

        # exits on 5m OHLC (stop first)
        if pos == 1:
            if m5l[j] <= sl:
                close_pos(sl, True)
            elif m5h[j] >= tp:
                close_pos(tp, False)
        elif pos == -1:
            if m5h[j] >= sl:
                close_pos(sl, True)
            elif m5l[j] <= tp:
                close_pos(tp, False)

        px = float(m5c[j])
        lo, hi = float(m5l[j]), float(m5h[j])

        mss_dir = 0  # +1 bullish MSS, -1 bearish MSS on this 5m bar
        if use_mss:
            if not np.isnan(ph5[j]):
                lsh5 = ph5[j]
            if not np.isnan(pl5[j]):
                lsl5 = pl5[j]
            if state5 == -1:
                leg_lo = min(leg_lo, lo)
            elif state5 == 1:
                leg_hi = max(leg_hi, hi)
            if state5 != -1 and not np.isnan(lsl5) and px < lsl5:
                if state5 == 1:
                    mss_dir = -1
                state5 = -1
                leg_lo = lo
            elif state5 != 1 and not np.isnan(lsh5) and px > lsh5:
                if state5 == -1:
                    mss_dir = 1
                state5 = 1
                leg_hi = hi

        if pos != 0 or h1_i < 0:
            continue

        d = int(bias[h1_i])
        if d == 1:
            ready = allow_long and b_fib_on and not b_entered
        elif d == -1:
            ready = allow_short and s_fib_on and not s_entered
        else:
            ready = False
        if not ready:
            continue

        tapped = long_zone_tap(lo, hi) if d == 1 else short_zone_tap(lo, hi)
        cur_fib = b_fib_bar if d == 1 else s_fib_bar
        if use_mss and tapped:
            arm_j[d] = j
            arm_fib[d] = cur_fib

        if start_asi8 is not None and m5_asi8[j] < start_asi8:
            continue
        if end_asi8 is not None and m5_asi8[j] >= end_asi8:
            continue

        if use_mss:
            if mss_dir != d or arm_fib[d] != cur_fib or j - arm_j[d] > p.arm_max_bars:
                continue
            if p.ltf_sl == "leg_low":
                stop = float(leg_lo if d == 1 else leg_hi)
            else:
                stop = float(lsl5 if d == 1 else lsh5)
            if np.isnan(stop):
                continue
            open_pos(d, px, stop)
        else:
            ev = bull_ifvg if d == 1 else bear_ifvg
            if not ev[j] or not tapped:
                continue
            stop = float(b_fib_lo if d == 1 else s_fib_hi)
            open_pos(d, px, stop)

    if pos != 0:
        close_pos(float(m5c[-1]), True)

    trades = len(pnl_list)
    wins = sum(1 for x in pnl_list if x > 0)
    gross_win = sum(x for x in pnl_list if x > 0)
    gross_loss = abs(sum(x for x in pnl_list if x <= 0))
    pf = gross_win / gross_loss if gross_loss > 0 else (99.0 if wins else 0.0)
    pnl = sum(pnl_list)
    m = Metrics(
        trades=trades,
        wins=wins,
        wr=100.0 * wins / trades if trades else 0.0,
        pf=pf,
        pnl=pnl,
        pnl_pct=100.0 * pnl / p.initial_capital,
        max_dd=max_dd,
        max_dd_pct=max_dd_pct,
        avg_r=float(np.mean(r_list)) if r_list else 0.0,
    )
    m.r_list = list(r_list)  # type: ignore[attr-defined]
    m.side_stats = {  # type: ignore[attr-defined]
        name: {
            "trades": len(v),
            "wr": 100.0 * sum(1 for x in v if x > 0) / len(v) if v else 0.0,
            "pnl_pct": 100.0 * sum(v) / p.initial_capital,
        }
        for name, v in (("long", side_pnl[1]), ("short", side_pnl[-1]))
    }
    return m


def resolve_paths():
    h1 = DATA / "btcusdt_1h.csv"
    if not h1.exists():
        h1 = DATA / "btcusdt_1h_bitget.csv"
    m5 = DATA / "btcusdt_5m_bitget.csv"
    return h1, m5


def load_market():
    h1_path, m5_path = resolve_paths()
    h1 = load_csv(h1_path)
    m5 = load_csv(m5_path)
    start = max(h1.index.min(), m5.index.min())
    h1 = h1.loc[h1.index >= start].copy()
    m5 = m5.loc[m5.index >= start].copy()
    end = min(h1.index.max(), m5.index.max())
    holdout_from = end - pd.Timedelta(days=HOLDOUT_DAYS)
    search_to = holdout_from
    search_from = search_to - pd.Timedelta(days=SEARCH_DAYS)
    data_min = start
    if search_from < data_min + pd.Timedelta(days=WARM_DAYS):
        search_from = data_min + pd.Timedelta(days=WARM_DAYS)
    warm_from = max(data_min, search_from - pd.Timedelta(days=WARM_DAYS))
    h1 = h1.loc[h1.index >= warm_from].copy()
    m5 = m5.loc[m5.index >= warm_from].copy()
    return {
        "h1": h1,
        "m5": m5,
        "search_from": search_from,
        "search_to": search_to,
        "holdout_from": holdout_from,
        "end": end,
        "h1_path": str(h1_path),
        "m5_path": str(m5_path),
    }


def jobs_list(trigger: str = "ifvg") -> list[dict]:
    """trigger: ifvg | mss | all (ifvg + mss jobs)."""
    jobs: list[dict] = []
    if trigger in ("ifvg", "all"):
        jobs += [
            dict(trigger="ifvg", swing=s, fib=f, risk=r)
            for s, f, r in itertools.product(SWINGS, FIB_MODES, RISK_MODES)
        ]
    if trigger in ("mss", "all"):
        jobs += [
            dict(trigger="mss", swing=s, fib=f, risk="size_cap", ltf_swing=ls, ltf_sl=sl)
            for s, f, ls, sl in itertools.product(SWINGS, FIB_MODES, LTF_SWINGS, LTF_SLS)
        ]
    return jobs


def job_from_row(r: pd.Series) -> dict:
    job = dict(trigger=r.trigger, swing=int(r.swing_len), fib=r.fib_mode, risk=r.risk_mode)
    if r.trigger == "mss":
        job.update(ltf_swing=int(r.ltf_swing_len), ltf_sl=r.ltf_sl)
    return job


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


def run_one(
    side: str,
    mkt: dict,
    swing: int,
    fib: str,
    risk: str,
    *,
    holdout: bool,
    trigger: str = "ifvg",
    ltf_swing: int = 3,
    ltf_sl: str = "leg_low",
) -> dict:
    p = SimpleParams(
        side=side,  # type: ignore
        swing_len=int(swing),
        fib_mode=fib,  # type: ignore
        risk_mode=risk,  # type: ignore
        trigger=trigger,  # type: ignore
        ltf_swing_len=int(ltf_swing),
        ltf_sl=ltf_sl,  # type: ignore
    )
    if holdout:
        start, end = mkt["holdout_from"], mkt["end"]
    else:
        start, end = mkt["search_from"], mkt["search_to"]
    m = backtest_simple(mkt["h1"], mkt["m5"], p, start_ts=start, end_ts=end)
    if trigger == "mss":
        trig = {
            "ltf_swing_len": int(ltf_swing),
            "ltf_sl": ltf_sl,
            "entry": "zone tap arms, 5m MSS fires",
            "fill": "5m_close_on_mss",
            "sl": f"5m {ltf_sl}",
        }
    else:
        trig = {
            "ltf_swing_len": np.nan,
            "ltf_sl": "",
            "entry": "discount_fvg_ob + 5m_ifvg_live",
            "fill": "5m_close_on_invasion",
            "sl": "fib_extreme",
        }
    ss = m.side_stats  # type: ignore[attr-defined]
    trig.update(
        long_trades=ss["long"]["trades"],
        long_wr=round(ss["long"]["wr"], 2),
        long_pnl_pct=round(ss["long"]["pnl_pct"], 2),
        short_trades=ss["short"]["trades"],
        short_wr=round(ss["short"]["wr"], 2),
        short_pnl_pct=round(ss["short"]["pnl_pct"], 2),
    )
    return {
        "side": side,
        "trigger": trigger,
        "swing_len": swing,
        "min_swing_atr": MIN_SWING_ATR,
        "fib_mode": fib,
        "risk_mode": risk,
        **trig,
        "bias_sweep_mode": "need_color",
        "bias_filter": "aligned",
        "tp": "2R",
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


def run_grid(side: str, resume: bool = False, trigger: str = "ifvg") -> Path:
    work = Path(os.environ.get("TEMP", str(OUT))) / f"simple_ict_{trigger}_{side}"
    work.mkdir(parents=True, exist_ok=True)
    log = work / "run.log"
    out_csv = work / "search_rows.csv"

    def log_msg(msg: str) -> None:
        print(msg, flush=True)
        with open(log, "a", encoding="utf-8") as f:
            f.write(datetime.now().isoformat() + " " + msg + "\n")

    mkt = load_market()
    jobs = jobs_list(trigger)
    log_msg(f"side={side} trigger={trigger} combos={len(jobs)}")
    log_msg(f"search {mkt['search_from'].date()} .. {mkt['search_to'].date()}")
    log_msg(f"holdout {mkt['holdout_from'].date()} .. {mkt['end'].date()}")
    if not resume and out_csv.exists():
        out_csv.unlink()
    done = 0
    prev = None
    if resume and out_csv.exists():
        prev = pd.read_csv(out_csv)
        done = len(prev)
        log_msg(f"resume {done}")
    total = len(jobs)
    while done < total:
        end = min(done + CHUNK, total)
        rows = [run_one(side, mkt, **jobs[i], holdout=False) for i in range(done, end)]
        cdf = pd.DataFrame(rows)
        if prev is None:
            cdf.to_csv(out_csv, index=False)
            prev = cdf
        else:
            cdf.to_csv(out_csv, mode="a", header=False, index=False)
            prev = pd.concat([prev, cdf], ignore_index=True)
        done = end
        log_msg(f"[{side}] {done}/{total}")

    df = pd.read_csv(out_csv)
    df["balance_score"] = balance_score(df)
    df = df.sort_values(["balance_score", "pf", "pnl_pct"], ascending=False).reset_index(drop=True)
    df.insert(0, "rank", np.arange(1, len(df) + 1))

    hold_rows = []
    for i in range(min(20, len(df))):
        r = df.iloc[i]
        h = run_one(side, mkt, **job_from_row(r), holdout=True)
        h["search_rank"] = int(r["rank"])
        h["search_score"] = float(r["balance_score"])
        hold_rows.append(h)
    hold_df = pd.DataFrame(hold_rows)
    if len(hold_df):
        hold_df["balance_score"] = balance_score(hold_df, min_trades=3)
        hold_df = hold_df.sort_values(
            ["balance_score", "pf", "pnl_pct"], ascending=False
        ).reset_index(drop=True)
        hold_df.insert(0, "holdout_rank", np.arange(1, len(hold_df) + 1))

    def axis_sum(col: str) -> pd.DataFrame:
        return (
            df.groupby(col)
            .agg(
                med_pf=("pf", "median"),
                med_pnl=("pnl_pct", "median"),
                med_trades=("trades", "median"),
                best=("balance_score", "max"),
            )
            .reset_index()
        )

    compares = {
        "Swing1H_Compare": axis_sum("swing_len"),
        "FibMode_Compare": axis_sum("fib_mode"),
    }
    if trigger == "all":
        compares["Trigger_Compare"] = axis_sum("trigger")
    if trigger in ("mss", "all"):
        mss_df = df[df.trigger == "mss"]
        for col, name in (("ltf_swing_len", "LtfSwing_Compare"), ("ltf_sl", "LtfSl_Compare")):
            compares[name] = (
                mss_df.groupby(col)
                .agg(med_pf=("pf", "median"), med_pnl=("pnl_pct", "median"), best=("balance_score", "max"))
                .reset_index()
            )
    if trigger in ("ifvg", "all"):
        compares["RiskMode_Compare"] = axis_sum("risk_mode")

    direction = {
        "long": "long only, bullish bias days",
        "short": "short only, bearish bias days",
        "both": "one book: bullish bias = long setups only, bearish bias = short setups only, uncertain = flat",
    }[side]
    logic = (
        "bias need_color decides direction; 1H fib + discount/premium FVG/OB; "
        "trigger ifvg (5m IFVG live, SL fib extreme) or mss (zone tap arms, 5m MSS, SL prev 5m swing); 2R"
    )
    fill = f"5m close on trigger bar; mss tap stays armed {ARM_MAX_BARS} 5m bars"
    sweep = {
        "ifvg": "1H swing x fib_mode x risk_mode",
        "mss": "1H swing x fib_mode x 5m swing x 5m SL; risk size_cap",
        "all": "ifvg grid + mss grid in one table",
    }[trigger]
    tag = {"ifvg": "simple", "mss": "mss", "all": "all"}[trigger]

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    xlsx = OUT / f"{side}_{tag}_{stamp}.xlsx"
    OUT.mkdir(parents=True, exist_ok=True)
    notes = pd.DataFrame(
        [
            {"item": "direction", "value": direction},
            {"item": "logic", "value": logic},
            {"item": "fill", "value": fill},
            {"item": "risk", "value": "size_cap=always 5% equity; skip_if_far=skip if SL>5% of price else 5% equity"},
            {"item": "sweep", "value": sweep},
            {"item": "search", "value": f"{mkt['search_from'].date()} .. {mkt['search_to'].date()}"},
            {"item": "holdout", "value": f"{mkt['holdout_from'].date()} .. {mkt['end'].date()}"},
        ]
    )
    with pd.ExcelWriter(xlsx, engine="xlsxwriter") as xw:
        df.head(1).to_excel(xw, sheet_name="Search_Champ", index=False)
        hold_df.head(1).to_excel(xw, sheet_name="Holdout_Champ", index=False)
        for name, sdf in compares.items():
            sdf.to_excel(xw, sheet_name=name, index=False)
        df.head(50).to_excel(xw, sheet_name="Search_Top50", index=False)
        hold_df.to_excel(xw, sheet_name="Holdout_Top20", index=False)
        df.to_excel(xw, sheet_name="Search_All", index=False)
        notes.to_excel(xw, sheet_name="Notes", index=False)
    log_msg(f"Wrote {xlsx}")
    if len(df):
        log_msg(f"SEARCH#1 {df.iloc[0].to_dict()}")
    if len(hold_df):
        log_msg(f"HOLDOUT#1 {hold_df.iloc[0].to_dict()}")
    return xlsx


def cli_main(side: str, argv: list[str]) -> int:
    import argparse
    import json

    ap = argparse.ArgumentParser(description=f"Simple ICT {side}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("grid")
    g.add_argument("--trigger", choices=["ifvg", "mss", "all"], default="ifvg")
    g.add_argument("--resume", action="store_true")
    b = sub.add_parser("backtest")
    b.add_argument("--trigger", choices=["ifvg", "mss"], default="ifvg")
    b.add_argument("--swing", type=int, default=12)
    b.add_argument("--fib", choices=["immediate", "wait"], default="immediate")
    b.add_argument("--risk", choices=["size_cap", "skip_if_far"], default="size_cap")
    b.add_argument("--ltf-swing", type=int, default=3, help="5m pivot length (mss)")
    b.add_argument("--ltf-sl", choices=["leg_low", "pivot"], default="leg_low", help="5m stop (mss)")
    args = ap.parse_args(argv)
    if args.cmd == "grid":
        print(run_grid(side, resume=args.resume, trigger=args.trigger))
        return 0
    mkt = load_market()
    kw = dict(
        swing=args.swing,
        fib=args.fib,
        risk=args.risk,
        trigger=args.trigger,
        ltf_swing=args.ltf_swing,
        ltf_sl=args.ltf_sl,
    )
    out = {
        "search": run_one(side, mkt, **kw, holdout=False),
        "holdout": run_one(side, mkt, **kw, holdout=True),
    }
    print(json.dumps(out, indent=2, default=str))
    return 0
