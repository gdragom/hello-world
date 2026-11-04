"""
LEDGER ICT 1H — local backtest engine (Python port of strategy v0.8 core).

Not bit-identical to TradingView (pivot/ATR edge cases differ), but close enough
for parameter ranking. Always Confirm top combos on TV Strategy Tester.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Literal

import numpy as np
import pandas as pd

EntryMode = Literal["zone_fvg_ob", "deep", "zone_only"]
FibMode = Literal["immediate", "wait"]
BiasFilter = Literal["off", "block_opp", "aligned"]
ShortFilter = Literal["match", "aligned", "no_bull", "long_only"]
SlMode = Literal["fib", "atr", "signal", "fixed_usd"]
# MSS = break that flips lastBreakSide (Pine); BOS = same-side continuation
StructGate = Literal["any", "mss", "bos"]
# need_color = legacy (sweep requires matching candle color; color path ignores mid)
# ignore_color = sweep sets bias without color; color path needs close vs mid
BiasSweepMode = Literal["need_color", "ignore_color"]


@dataclass(frozen=True)
class Params:
    swing_len: int = 5
    min_swing_atr: float = 0.5
    atr_len: int = 14
    fib_mode: FibMode = "immediate"
    entry_mode: EntryMode = "deep"
    bias_filter: BiasFilter = "block_opp"
    short_filter: ShortFilter = "no_bull"
    rr_mult: float = 2.0
    sl_mode: SlMode = "fib"
    fallback_atr_sl: float = 1.5
    fixed_usd_sl: float = 500.0
    zone_keep: int = 80
    max_zones: int = 12
    reenter: bool = False
    cooldown: int = 6
    post_stop_cooldown: int = 8
    lock_fib_on_stop: bool = True
    min_hold_bars: int = 4
    be_trigger_r: float = 1.0  # 0 = off
    risk_pct: float = 1.0
    doji_body_pct: float = 10.0
    require_body: bool = True
    commission_pct: float = 0.04  # per side
    initial_capital: float = 10_000.0
    eq_wick: bool = False  # True: 1H low tags 0.5; False: close must be ≤ 0.5
    use_fixed_dollar: bool = False
    fixed_tp_usd: float = 1000.0
    fixed_risk_usd: float = 500.0
    allow_long: bool = True  # False = short-only book
    bias_sweep_mode: BiasSweepMode = "need_color"
    htf_sma_gate: bool = False  # Short only: sealed daily close < SMA fast and SMA slow
    htf_sma_fast: int = 50
    htf_sma_slow: int = 200
    struct_gate: StructGate = "any"

@dataclass
class Metrics:
    trades: int = 0
    wins: int = 0
    wr: float = 0.0
    pf: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    max_dd: float = 0.0
    max_dd_pct: float = 0.0
    avg_r: float = 0.0

    def score(self) -> float:
        """Rank score: prefer PF with trade-count and DD guards."""
        if self.trades < 15:
            return -1e9
        if self.max_dd_pct > 35:
            return -1e9
        # Soft target ~80–200 trades / year handled by caller via slice length
        return self.pf * 100.0 + self.pnl_pct - self.max_dd_pct * 0.5


def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, length: int) -> np.ndarray:
    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))
    out = np.full_like(tr, np.nan, dtype=float)
    if len(tr) < length:
        return out
    out[length - 1] = np.mean(tr[:length])
    alpha = 1.0 / length
    for i in range(length, len(tr)):
        out[i] = out[i - 1] * (1 - alpha) + tr[i] * alpha
    return out


def _pivots(high: np.ndarray, low: np.ndarray, left: int, right: int):
    """Match ta.pivothigh / ta.pivotlow (ties allowed — TV still returns the pivot)."""
    n = len(high)
    ph = np.full(n, np.nan)
    pl = np.full(n, np.nan)
    for i in range(left, n - right):
        window_h = high[i - left : i + right + 1]
        window_l = low[i - left : i + right + 1]
        if high[i] == np.max(window_h):
            ph[i + right] = high[i]  # confirm on right edge bar (TV style)
        if low[i] == np.min(window_l):
            pl[i + right] = low[i]
    return ph, pl


def _htf_sma_bear(df: pd.DataFrame, fast: int, slow: int) -> np.ndarray:
    """True on 1H bars when last completed daily close is below SMA(fast) and SMA(slow)."""
    daily = df.resample("1D").agg({"close": "last"}).dropna()
    sealed = daily["close"].shift(1)
    sma_f = sealed.rolling(fast, min_periods=fast).mean()
    sma_s = sealed.rolling(slow, min_periods=slow).mean()
    ok = (sealed < sma_f) & (sealed < sma_s)
    mapped = ok.astype(float).reindex(df.index, method="ffill")
    return (mapped.fillna(0.0).to_numpy() > 0.5)


def _daily_bias(
    df: pd.DataFrame,
    doji_pct: float,
    sweep_mode: BiasSweepMode = "need_color",
) -> np.ndarray:
    """biasDir per 1H bar: 1 long, -1 short, 0 uncertain. Uses completed days only.

    need_color (legacy): PDL/PDH sweep only counts with matching candle color;
    color-only path uses open/close color (no mid filter).

    ignore_color: single sweep sets bias regardless of color; color-only path
    requires close above/below daily mid (0.5 of high-low).
    """
    o = df["open"].to_numpy()
    h = df["high"].to_numpy()
    l = df["low"].to_numpy()
    c = df["close"].to_numpy()
    idx = df.index
    n = len(df)
    bias = np.zeros(n, dtype=int)

    days = pd.Series(idx.date, index=idx)
    unique_days = list(dict.fromkeys(days))
    day_ohlc = {}
    for d in unique_days:
        mask = days == d
        day_ohlc[d] = (
            float(o[mask][0]),
            float(np.max(h[mask])),
            float(np.min(l[mask])),
            float(c[mask][-1]),
        )

    sealed: dict = {}
    ignore = sweep_mode == "ignore_color"
    for i, d in enumerate(unique_days):
        if i < 2:
            sealed[d] = 0
            continue
        y = unique_days[i - 1]
        b = unique_days[i - 2]
        yO, yH, yL, yC = day_ohlc[y]
        _, bH, bL, _ = day_ohlc[b]
        rng = yH - yL
        is_doji = rng > 0 and abs(yC - yO) / rng * 100.0 <= doji_pct
        is_bull = yC > yO
        is_bear = yC < yO
        mid = yL + 0.5 * rng if rng > 0 else yC
        close_above_mid = yC > mid
        close_below_mid = yC < mid
        pdl = yL < bL and yC > bL
        pdh = yH > bH and yC < bH

        if is_doji:
            bd = 0
        elif pdl and pdh:
            bd = 0
        elif pdl:
            if ignore:
                bd = 1
            else:
                bd = 1 if is_bull else 0
        elif pdh:
            if ignore:
                bd = -1
            else:
                bd = -1 if is_bear else 0
        else:
            if ignore:
                if is_bull and close_above_mid:
                    bd = 1
                elif is_bear and close_below_mid:
                    bd = -1
                else:
                    bd = 0
            else:
                if is_bull:
                    bd = 1
                elif is_bear:
                    bd = -1
                else:
                    bd = 0
        sealed[d] = bd

    for i in range(n):
        bias[i] = sealed.get(days.iloc[i], 0)
    return bias


def backtest(
    df: pd.DataFrame,
    p: Params,
    ifvg_ok: np.ndarray | None = None,
    start_i: int = 0,
    collect_trades: bool = False,
    collect_trace: bool = False,
) -> Metrics:
    """Run one backtest on OHLC DataFrame (DatetimeIndex, columns open high low close).

    ifvg_ok: optional bool array, True when a fresh 5m bullish IFVG is in age window.
    start_i: ignore entries before this bar (structure still warms up).
    collect_trades: attach entry/exit rows to Metrics.trade_log (not in score path).
    collect_trace: attach fib/FVG/BOS events to Metrics.trace for visual parity tools.
    """
    trade_log: list = []
    trace: dict = {
        "fibs": [],  # {side,t0,t1,eq,lo,hi}
        "fvgs": [],  # {side,t0,t1,top,bot}
        "bos": [],  # {side,time,level}
    }
    open_fib: dict | None = None  # long fib segment being built
    open_fvgs: list[dict] = []  # live bull FVG boxes still open

    def _ts(i: int) -> str:
        return str(idx[i])

    def _close_fib(i: int) -> None:
        nonlocal open_fib
        if open_fib is None:
            return
        open_fib["t1"] = _ts(i)
        trace["fibs"].append(open_fib)
        open_fib = None

    def _arm_fib(i: int, eq: float, lo: float, hi: float) -> None:
        nonlocal open_fib
        _close_fib(i)
        open_fib = {
            "side": "long",
            "t0": _ts(i),
            "t1": _ts(i),
            "eq": float(eq),
            "lo": float(lo),
            "hi": float(hi),
        }

    def _update_fib_levels(eq: float, lo: float, hi: float) -> None:
        if open_fib is None:
            return
        open_fib["eq"] = float(eq)
        open_fib["lo"] = float(lo)
        open_fib["hi"] = float(hi)

    def _close_expired_fvgs(i: int) -> None:
        still = []
        for box in open_fvgs:
            if not box.get("_live", True):
                box["t1"] = _ts(i)
                trace["fvgs"].append({k: v for k, v in box.items() if not k.startswith("_")})
            else:
                still.append(box)
        open_fvgs[:] = still

    df = df.sort_index()
    o = df["open"].to_numpy(float)
    h = df["high"].to_numpy(float)
    l = df["low"].to_numpy(float)
    c = df["close"].to_numpy(float)
    idx = df.index
    n = len(df)
    if n < p.swing_len * 3 + 50:
        m = Metrics()
        if collect_trades:
            m.trade_log = trade_log  # type: ignore[attr-defined]
        if collect_trace:
            m.trace = trace  # type: ignore[attr-defined]
        return m

    atr = _atr(h, l, c, p.atr_len)
    ph_raw, pl_raw = _pivots(h, l, p.swing_len, p.swing_len)
    bias = _daily_bias(df, p.doji_body_pct, p.bias_sweep_mode)
    htf_bear = (
        _htf_sma_bear(df, p.htf_sma_fast, p.htf_sma_slow)
        if p.htf_sma_gate
        else np.ones(n, dtype=bool)
    )

    last_sh = np.nan
    last_sl = np.nan
    last_sh_bar = -1
    last_sl_bar = -1
    last_break_side = 0

    b_bos = False
    b_bos_bar = -1
    b_level = np.nan
    b_prior_sl = np.nan
    b_fib_on = False
    b_fib_hi = b_fib_lo = b_eq = np.nan
    b_entered = False
    b_fib_bar = -1
    b_is_mss = False

    s_bos = False
    s_bos_bar = -1
    s_level = np.nan
    s_prior_sh = np.nan
    s_fib_on = False
    s_fib_hi = s_fib_lo = s_eq = np.nan
    s_entered = False
    s_fib_bar = -1
    s_is_mss = False

    # virgin zones: list of (top, bot, bar, live)
    bf, sf, bo, so = [], [], [], []

    equity = p.initial_capital
    peak = equity
    max_dd = 0.0
    max_dd_pct = 0.0
    pnl_list: list[float] = []
    r_list: list[float] = []

    pos = 0  # 1 long -1 short
    entry_px = sl = tp = qty = 0.0
    last_ent_bar = -10**9
    last_stop_bar = -10**9
    entry_bar = -1
    be_done = False
    risk_at_entry = 0.0
    risk_cash_at_entry = 0.0

    def bias_ok_long(i: int) -> bool:
        if not p.allow_long:
            return False
        bd = bias[i]
        if p.bias_filter == "off":
            return True
        if p.bias_filter == "block_opp":
            return bd != -1
        return bd == 1

    def bias_ok_short(i: int) -> bool:
        bd = bias[i]
        if p.short_filter == "long_only":
            return False
        if p.short_filter == "aligned":
            return bd == -1
        if p.short_filter == "no_bull":
            return bd != 1
        # match long bias filter
        if p.bias_filter == "off":
            return True
        if p.bias_filter == "block_opp":
            return bd != 1
        return bd == -1

    def push_zone(zones, top, bot, bar, *, kind: str = ""):
        zones.append([top, bot, bar, True])
        if len(zones) > p.max_zones:
            dead = zones.pop(0)
            if collect_trace and kind == "bf" and dead[3]:
                # oldest bull FVG evicted
                for box in open_fvgs:
                    if box.get("_bar") == dead[2] and box.get("_live"):
                        box["_live"] = False
        if collect_trace and kind == "bf":
            open_fvgs.append(
                {
                    "side": "long",
                    "t0": _ts(bar),
                    "t1": _ts(bar),
                    "top": float(top),
                    "bot": float(bot),
                    "_bar": bar,
                    "_live": True,
                }
            )

    def maintain(zones, is_bull, i, close_px):
        for z in zones:
            if not z[3]:
                continue
            kill = i - z[2] > p.zone_keep
            if is_bull and close_px < z[1]:
                kill = True
            elif (not is_bull) and close_px > z[0]:
                kill = True
            if kill:
                z[3] = False
                if collect_trace and is_bull:
                    for box in open_fvgs:
                        if box.get("_bar") == z[2] and box.get("_live"):
                            box["_live"] = False
                            box["t1"] = _ts(i)

    def hit_fvg(zones, i, lo, hi, eq, fib_lo, fib_hi, is_long):
        """Pine FVG overlap: gap straddles discount/premium band."""
        for zi, z in enumerate(zones):
            if not z[3] or i <= z[2]:
                continue
            t, b = z[0], z[1]
            if is_long:
                if b < eq and t > fib_lo and lo <= t and hi >= b:
                    return zi, b
            else:
                if t > eq and b < fib_hi and hi >= b and lo <= t:
                    return zi, t
        return -1, np.nan

    def hit_ob(zones, i, lo, hi, eq, fib_lo, fib_hi, is_long):
        """Pine OB: zone fully inside [floor, 0.5] (long) / [0.5, ceiling] (short)."""
        for zi, z in enumerate(zones):
            if not z[3] or i <= z[2]:
                continue
            t, b = z[0], z[1]
            if is_long:
                if b >= fib_lo and t <= eq and lo <= t and hi >= b:
                    return zi, b
            else:
                if b >= eq and t <= fib_hi and hi >= b and lo <= t:
                    return zi, t
        return -1, np.nan

    def close_pos(px, i, is_stop: bool):
        nonlocal pos, equity, peak, max_dd, max_dd_pct, entry_px, qty, last_stop_bar, be_done, entry_bar
        nonlocal b_entered, s_entered
        if pos == 0:
            return
        side = pos
        entry_i = entry_bar
        entry_price = entry_px
        entry_qty = qty
        gross = (px - entry_px) * qty * pos
        fee = (abs(entry_px) + abs(px)) * qty * (p.commission_pct / 100.0)
        net = gross - fee
        equity += net
        pnl_list.append(net)
        if risk_cash_at_entry > 0:
            r_list.append(net / risk_cash_at_entry)
        peak = max(peak, equity)
        dd = peak - equity
        max_dd = max(max_dd, dd)
        max_dd_pct = max(max_dd_pct, dd / peak * 100.0 if peak > 0 else 0.0)
        if collect_trades:
            trade_log.append(
                {
                    "side": "long" if side > 0 else "short",
                    "entry_time": str(idx[entry_i]),
                    "exit_time": str(idx[i]),
                    "entry_px": float(entry_price),
                    "exit_px": float(px),
                    "qty": float(entry_qty),
                    "pnl": float(net),
                    "is_stop": bool(is_stop),
                }
            )
        if is_stop or net <= 0:
            last_stop_bar = i
            if side > 0:
                b_entered = True
            else:
                s_entered = True
        elif p.reenter:
            if side > 0:
                b_entered = False
            else:
                s_entered = False
        pos = 0
        be_done = False
        entry_bar = -1

    for i in range(n):
        # BE ratchet before stop check
        if pos != 0 and p.be_trigger_r > 0 and not be_done and risk_at_entry > 0:
            if pos == 1:
                mfe_r = (h[i] - entry_px) / risk_at_entry
                if mfe_r >= p.be_trigger_r:
                    sl = max(sl, entry_px)
                    be_done = True
            else:
                mfe_r = (entry_px - l[i]) / risk_at_entry
                if mfe_r >= p.be_trigger_r:
                    sl = min(sl, entry_px)
                    be_done = True

        # manage open trade on this bar OHLC
        held = entry_bar < 0 or (i - entry_bar) >= p.min_hold_bars
        if pos == 1:
            if held and l[i] <= sl:
                close_pos(sl, i, True)
            elif h[i] >= tp:
                close_pos(tp, i, False)
        elif pos == -1:
            if held and h[i] >= sl:
                close_pos(sl, i, True)
            elif l[i] <= tp:
                close_pos(tp, i, False)
        a = atr[i]
        if np.isnan(a):
            continue
        min_dist = 0.0 if p.min_swing_atr <= 0 else a * p.min_swing_atr

        # pivots confirmed this bar
        if not np.isnan(ph_raw[i]):
            if min_dist <= 0 or np.isnan(last_sl) or (ph_raw[i] - last_sl) >= min_dist:
                last_sh = ph_raw[i]
                last_sh_bar = i - p.swing_len
        if not np.isnan(pl_raw[i]):
            if min_dist <= 0 or np.isnan(last_sh) or (last_sh - pl_raw[i]) >= min_dist:
                last_sl = pl_raw[i]
                last_sl_bar = i - p.swing_len

        body_top = max(o[i], c[i])
        body_bot = min(o[i], c[i])

        # FVG / OB form
        if i >= 2:
            if h[i - 2] < l[i] and l[i] > h[i - 2]:
                push_zone(bf, l[i], h[i - 2], i, kind="bf")
            if l[i - 2] > h[i]:
                push_zone(sf, l[i - 2], h[i], i, kind="sf")
        if i >= 1:
            if c[i - 1] < o[i - 1] and c[i] > h[i - 1]:
                push_zone(bo, o[i - 1], c[i - 1], i - 1, kind="bo")
            if c[i - 1] > o[i - 1] and c[i] < l[i - 1]:
                push_zone(so, c[i - 1], o[i - 1], i - 1, kind="so")

        # Note: zone maintain (age/fill kill) runs AFTER entries — matches Pine order
        # so a zone filled by this bar's close can still trigger entry.

        # kill fibs
        if b_fib_on and (i - b_fib_bar > 60 or c[i] < b_fib_lo):
            b_fib_on = False
            b_entered = False
            if collect_trace:
                _close_fib(i)
        if s_fib_on and (i - s_fib_bar > 60 or c[i] > s_fib_hi):
            s_fib_on = False
            s_entered = False
        if b_bos and not b_fib_on and not np.isnan(b_level) and c[i] < b_level:
            b_bos = False
        if s_bos and not s_fib_on and not np.isnan(s_level) and c[i] > s_level:
            s_bos = False

        # bull break
        bull_break = (not np.isnan(last_sh)) and c[i] > last_sh and (
            (not p.require_body) or body_top > last_sh
        )
        if bull_break and not b_bos and not b_fib_on:
            s_bos = s_fib_on = False
            s_entered = False
            b_is_mss = last_break_side == -1
            last_break_side = 1
            b_bos = True
            b_bos_bar = i
            b_level = last_sh
            b_prior_sl = last_sl
            b_entered = False
            if collect_trace:
                trace["bos"].append({"side": "long", "time": _ts(i), "level": float(b_level)})
            if p.fib_mode == "immediate":
                fib_hi = max(h[i], b_level)
                fib_lo = b_prior_sl if not np.isnan(b_prior_sl) else last_sl
                if not np.isnan(fib_lo) and fib_hi > fib_lo:
                    b_fib_hi, b_fib_lo = fib_hi, fib_lo
                    b_eq = b_fib_lo + (b_fib_hi - b_fib_lo) * 0.5
                    b_fib_on = True
                    b_fib_bar = i
                    b_bos = False
                    if collect_trace:
                        _arm_fib(i, b_eq, b_fib_lo, b_fib_hi)

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
                    if collect_trace:
                        _arm_fib(i, b_eq, b_fib_lo, b_fib_hi)

        # Pine: upgrade immediate fib when a higher post-BOS SH prints
        if (
            b_fib_on
            and p.fib_mode == "immediate"
            and not np.isnan(ph_raw[i])
            and (i - p.swing_len) > b_fib_bar
            and ph_raw[i] > b_fib_hi
            and not np.isnan(b_fib_lo)
            and ph_raw[i] > b_fib_lo
        ):
            b_fib_hi = ph_raw[i]
            b_eq = b_fib_lo + (b_fib_hi - b_fib_lo) * 0.5
            if collect_trace:
                _update_fib_levels(b_eq, b_fib_lo, b_fib_hi)
                # split segment so chart shows level change
                _close_fib(i)
                _arm_fib(i, b_eq, b_fib_lo, b_fib_hi)

        bear_break = (not np.isnan(last_sl)) and c[i] < last_sl and (
            (not p.require_body) or body_bot < last_sl
        )
        if bear_break and not s_bos and not s_fib_on:
            if collect_trace and b_fib_on:
                _close_fib(i)
            b_bos = b_fib_on = False
            b_entered = False
            s_is_mss = last_break_side == 1
            last_break_side = -1
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

        if p.reenter and pos == 0:
            # Pine: unlock after post-stop ban only (entry cooldown checked at entry)
            if (
                b_fib_on
                and b_entered
                and last_stop_bar > last_ent_bar
                and i - last_stop_bar >= p.post_stop_cooldown
            ):
                b_entered = False
            if (
                s_fib_on
                and s_entered
                and last_stop_bar > last_ent_bar
                and i - last_stop_bar >= p.post_stop_cooldown
            ):
                s_entered = False
        cool_stop = i - last_stop_bar >= p.post_stop_cooldown
        # entries
        if pos == 0 and i - last_ent_bar >= p.cooldown and cool_stop:
            struct_ok_l = (
                p.struct_gate == "any"
                or (p.struct_gate == "mss" and b_is_mss)
                or (p.struct_gate == "bos" and not b_is_mss)
            )
            struct_ok_s = (
                p.struct_gate == "any"
                or (p.struct_gate == "mss" and s_is_mss)
                or (p.struct_gate == "bos" and not s_is_mss)
            )
            if b_fib_on and not b_entered and bias_ok_long(i) and struct_ok_l:
                in_disc = l[i] <= b_eq and h[i] >= b_fib_lo
                deep = c[i] <= b_fib_lo + (b_eq - b_fib_lo) * 0.5
                zi_f, sig_b = hit_fvg(bf, i, l[i], h[i], b_eq, b_fib_lo, b_fib_hi, True)
                zi_o, sig_o = hit_ob(bo, i, l[i], h[i], b_eq, b_fib_lo, b_fib_hi, True)
                zone = zi_f >= 0 or zi_o >= 0
                if p.entry_mode == "zone_only":
                    cond = True
                elif p.entry_mode == "zone_fvg_ob":
                    cond = zone
                else:
                    cond = zone or deep
                eq_ok = l[i] <= b_eq if p.eq_wick else c[i] <= b_eq
                ifvg_pass = True if ifvg_ok is None else bool(ifvg_ok[i])
                if i >= start_i and in_disc and cond and eq_ok and ifvg_pass:
                    atr_sl = c[i] - a * p.fallback_atr_sl
                    fib_sl = b_fib_lo if b_fib_lo < c[i] else atr_sl
                    sig = sig_b if zi_f >= 0 else (sig_o if zi_o >= 0 else np.nan)
                    if p.use_fixed_dollar:
                        stop = c[i] - p.fixed_usd_sl
                    elif p.sl_mode == "atr":
                        stop = atr_sl
                    elif p.sl_mode == "fixed_usd":
                        stop = c[i] - p.fixed_usd_sl
                    elif p.sl_mode == "signal" and not np.isnan(sig) and sig < c[i]:
                        stop = sig
                    else:
                        stop = fib_sl
                    risk = c[i] - stop
                    if risk > 0:
                        if p.use_fixed_dollar:
                            q = p.fixed_risk_usd / max(p.fixed_usd_sl, 1e-9)
                            risk_cash = p.fixed_risk_usd
                        else:
                            risk_cash = equity * p.risk_pct / 100.0
                            q = risk_cash / risk
                            max_q = equity * 0.5 / c[i]
                            q = min(q, max_q)
                        if q > 0:
                            if pos != 0:
                                close_pos(c[i], i, True)
                            pos = 1
                            entry_px = c[i]
                            sl = stop
                            tp = (
                                c[i] + p.fixed_tp_usd / q
                                if p.use_fixed_dollar and q > 0
                                else c[i] + risk * p.rr_mult
                            )
                            qty = q
                            risk_at_entry = risk
                            risk_cash_at_entry = risk_cash
                            be_done = False
                            entry_bar = i
                            b_entered = True
                            last_ent_bar = i
                            if zi_f >= 0:
                                bf[zi_f][3] = False
                            if zi_o >= 0:
                                bo[zi_o][3] = False

            if pos == 0 and i >= start_i and s_fib_on and not s_entered and bias_ok_short(i) and struct_ok_s:
                in_prem = h[i] >= s_eq and l[i] <= s_fib_hi
                deep = c[i] >= s_eq + (s_fib_hi - s_eq) * 0.5
                zi_f, sig_t = hit_fvg(sf, i, l[i], h[i], s_eq, s_fib_lo, s_fib_hi, False)
                zi_o, sig_o = hit_ob(so, i, l[i], h[i], s_eq, s_fib_lo, s_fib_hi, False)
                zone = zi_f >= 0 or zi_o >= 0
                if p.entry_mode == "zone_only":
                    cond = True
                elif p.entry_mode == "zone_fvg_ob":
                    cond = zone
                else:
                    cond = zone or deep
                eq_ok = h[i] >= s_eq if p.eq_wick else c[i] >= s_eq
                ifvg_pass = True if ifvg_ok is None else bool(ifvg_ok[i])
                if in_prem and cond and eq_ok and ifvg_pass and bool(htf_bear[i]):
                    atr_sl = c[i] + a * p.fallback_atr_sl
                    fib_sl = s_fib_hi if s_fib_hi > c[i] else atr_sl
                    sig = sig_t if zi_f >= 0 else (sig_o if zi_o >= 0 else np.nan)
                    if p.use_fixed_dollar:
                        stop = c[i] + p.fixed_usd_sl
                    elif p.sl_mode == "atr":
                        stop = atr_sl
                    elif p.sl_mode == "fixed_usd":
                        stop = c[i] + p.fixed_usd_sl
                    elif p.sl_mode == "signal" and not np.isnan(sig) and sig > c[i]:
                        stop = sig
                    else:
                        stop = fib_sl
                    risk = stop - c[i]
                    if risk > 0:
                        if p.use_fixed_dollar:
                            q = p.fixed_risk_usd / max(p.fixed_usd_sl, 1e-9)
                            risk_cash = p.fixed_risk_usd
                        else:
                            risk_cash = equity * p.risk_pct / 100.0
                            q = risk_cash / risk
                            max_q = equity * 0.5 / c[i]
                            q = min(q, max_q)
                        if q > 0:
                            pos = -1
                            entry_px = c[i]
                            sl = stop
                            tp = (
                                c[i] - p.fixed_tp_usd / q
                                if p.use_fixed_dollar and q > 0
                                else c[i] - risk * p.rr_mult
                            )
                            qty = q
                            risk_at_entry = risk
                            risk_cash_at_entry = risk_cash
                            be_done = False
                            entry_bar = i
                            s_entered = True
                            last_ent_bar = i
                            if zi_f >= 0:
                                sf[zi_f][3] = False
                            if zi_o >= 0:
                                so[zi_o][3] = False

        # Pine: maintain zones after entry scan
        maintain(bf, True, i, c[i])
        maintain(sf, False, i, c[i])
        maintain(bo, True, i, c[i])
        maintain(so, False, i, c[i])
        if collect_trace:
            _close_expired_fvgs(i)

    # flatten
    if pos != 0:
        close_pos(c[-1], n - 1, True)
    if collect_trace:
        if open_fib is not None:
            _close_fib(n - 1)
        for box in open_fvgs:
            box["t1"] = _ts(n - 1)
            trace["fvgs"].append({k: v for k, v in box.items() if not k.startswith("_")})
        open_fvgs.clear()
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
    if collect_trades:
        m.trade_log = trade_log  # type: ignore[attr-defined]
    if collect_trace:
        m.trace = trace  # type: ignore[attr-defined]
    return m


def params_to_row(p: Params, m: Metrics, tag: str = "") -> dict:
    d = asdict(p)
    d.update(asdict(m))
    d["tag"] = tag
    d["rank_score"] = m.score()
    return d
