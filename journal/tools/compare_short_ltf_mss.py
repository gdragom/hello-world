#!/usr/bin/env python3
"""Short Custom pack 2019+: 5m IFVG vs 5m MSS (CHoCH) as the LTF trigger."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ledger_engine import Params, backtest, _pivots  # noqa: E402
from parity_tv_last365 import bull_ifvg_ok, load_csv  # noqa: E402
from param_lab.serve import bear_ifvg_ok  # noqa: E402

H1 = ROOT / "data" / "btcusdt_1h_bitget.csv"
M5 = ROOT / "data" / "btcusdt_5m_bitget.csv"


def pack_short() -> Params:
    return Params(
        swing_len=8,
        min_swing_atr=0.6,
        atr_len=14,
        fib_mode="immediate",
        entry_mode="zone_fvg_ob",
        bias_filter="aligned",
        short_filter="match",
        rr_mult=2.0,
        sl_mode="fixed_usd",
        fixed_usd_sl=1000.0,
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
        fixed_tp_usd=2000.0,
        fixed_risk_usd=500.0,
        allow_long=False,
    )


def pack_long() -> Params:
    p = pack_short()
    return Params(
        **{
            **p.__dict__,
            "fixed_usd_sl": 500.0,
            "fixed_tp_usd": 1000.0,
            "short_filter": "long_only",
            "allow_long": True,
        }
    )


def ltf_mss_ok(
    h1: pd.DataFrame,
    ltf: pd.DataFrame,
    max_age: int,
    swing_len: int,
    *,
    bear: bool,
    htf_minutes: int = 60,
) -> np.ndarray:
    """Map LTF MSS (CHoCH) age onto 1H bars — same merge as IFVG.

    MSS = swing break that *flips* last break side (Pine lastBreakSide).
    """
    o = ltf["open"].to_numpy(float)
    h = ltf["high"].to_numpy(float)
    l = ltf["low"].to_numpy(float)
    c = ltf["close"].to_numpy(float)
    n = len(ltf)
    ph, pl = _pivots(h, l, swing_len, swing_len)
    last_sh = np.nan
    last_sl = np.nan
    last_break = 0  # 1 bull, -1 bear
    age = np.full(n, 10_000, dtype=int)
    last_event = -10_000
    for i in range(n):
        if not np.isnan(ph[i]):
            last_sh = ph[i]
        if not np.isnan(pl[i]):
            last_sl = pl[i]
        body_top = max(o[i], c[i])
        body_bot = min(o[i], c[i])
        bull_break = (not np.isnan(last_sh)) and c[i] > last_sh and body_top > last_sh
        bear_break = (not np.isnan(last_sl)) and c[i] < last_sl and body_bot < last_sl
        # Always track both break sides so MSS = flip (Pine lastBreakSide).
        if bull_break:
            if (not bear) and last_break == -1:
                last_event = i
            last_break = 1
        elif bear_break:
            if bear and last_break == 1:
                last_event = i
            last_break = -1
        if last_event >= 0:
            age[i] = i - last_event
    htf_close = h1.index + pd.Timedelta(minutes=htf_minutes)
    pos = np.searchsorted(ltf.index.asi8, htf_close.asi8, side="left") - 1
    ok = np.zeros(len(h1), dtype=bool)
    valid = pos >= 0
    ok[valid] = age[pos[valid]] <= max_age
    return ok


def combine(a: np.ndarray | None, b: np.ndarray | None) -> np.ndarray | None:
    if a is None:
        return b
    if b is None:
        return a
    return a & b


def fmt(m, label: str) -> None:
    print(
        f"{label:22s} n={m.trades:3d} WR={m.wr:5.1f}% PF={m.pf:5.3f} "
        f"PnL%={m.pnl_pct:7.1f} DD={m.max_dd_pct:5.1f}%",
        flush=True,
    )


def main() -> int:
    h1 = load_csv(H1)
    m5 = load_csv(M5)
    print(f"H1 {len(h1)} {h1.index.min().date()} .. {h1.index.max().date()}", flush=True)
    ps = pack_short()
    pl = pack_long()

    bull_ifvg = bull_ifvg_ok(h1, m5, 6)
    bear_ifvg = bear_ifvg_ok(h1, m5, 6)
    bear_mss5 = ltf_mss_ok(h1, m5, 12, 5, bear=True)
    bear_mss8 = ltf_mss_ok(h1, m5, 12, 8, bear=True)
    bear_mss6age = ltf_mss_ok(h1, m5, 6, 5, bear=True)
    bull_mss5 = ltf_mss_ok(h1, m5, 12, 5, bear=False)

    print("--- LONG (ref) ---", flush=True)
    fmt(backtest(h1, pl, ifvg_ok=bull_ifvg, start_i=0), "1H + 5m IFVG@6")
    fmt(backtest(h1, pl, ifvg_ok=bull_mss5, start_i=0), "1H + 5m MSS sw5@12")

    print("--- SHORT ---", flush=True)
    rows = [
        ("no LTF", None),
        ("5m IFVG@6", bear_ifvg),
        ("5m MSS sw5@12", bear_mss5),
        ("5m MSS sw8@12", bear_mss8),
        ("5m MSS sw5@6", bear_mss6age),
        ("IFVG AND MSS5", combine(bear_ifvg, bear_mss5)),
    ]
    for name, gate in rows:
        fmt(backtest(h1, ps, ifvg_ok=gate, start_i=0), name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
