#!/usr/bin/env python3
"""Short Custom pack: skip entries when HTF BTC is still bullish.

Daily series is sealed (yesterday's close) so a 1H bar never sees the forming day.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ledger_engine import Params, backtest
from parity_tv_last365 import load_csv
from param_lab.serve import bear_ifvg_ok

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
        fixed_usd_sl=750.0,
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
        fixed_tp_usd=1500.0,
        fixed_risk_usd=500.0,
        allow_long=False,
    )


def sealed_daily(h1: pd.DataFrame) -> pd.DataFrame:
    d = h1.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    # Use yesterday only: shift so today's 1H bars see last completed daily bar.
    return d.shift(1).dropna()


def map_daily_to_h1(h1: pd.DataFrame, daily: pd.Series) -> np.ndarray:
    s = daily.reindex(h1.index, method="ffill")
    return s.to_numpy(dtype=float)


def fmt(m, label: str, allow: np.ndarray) -> None:
    pct = 100.0 * float(np.mean(allow)) if len(allow) else 0.0
    print(
        f"{label:28s} n={m.trades:3d} WR={m.wr:5.1f}% PF={m.pf:5.3f} "
        f"PnL%={m.pnl_pct:7.1f} DD={m.max_dd_pct:5.1f}%  bars_on={pct:4.0f}%",
        flush=True,
    )


def main() -> int:
    h1 = load_csv(H1)
    m5 = load_csv(M5)
    print(f"H1 {len(h1)} {h1.index.min()} .. {h1.index.max()}", flush=True)
    print("Short pack + 5m IFVG@6; extra gate = HTF bear only", flush=True)

    d = sealed_daily(h1)
    dc = d["close"]
    ret = lambda n: (dc / dc.shift(n) - 1.0)

    gates: list[tuple[str, pd.Series]] = [
        ("no HTF gate", pd.Series(True, index=d.index)),
        ("1D ret 30d < 0", ret(30) < 0),
        ("1D ret 90d < 0", ret(90) < 0),
        ("1D ret 180d < 0", ret(180) < 0),
        ("1D ret 365d < 0", ret(365) < 0),
        ("close < SMA50D", dc < dc.rolling(50).mean()),
        ("close < SMA200D", dc < dc.rolling(200).mean()),
        ("<SMA50 and <SMA200", (dc < dc.rolling(50).mean()) & (dc < dc.rolling(200).mean())),
        ("ret90<0 and <SMA200", (ret(90) < 0) & (dc < dc.rolling(200).mean())),
        ("ret180<0 or <SMA200", (ret(180) < 0) | (dc < dc.rolling(200).mean())),
    ]

    print("Building 5m IFVG…", flush=True)
    bear = bear_ifvg_ok(h1, m5, 6)
    p = pack_short()

    for label, g in gates:
        allow_d = g.fillna(False).astype(bool)
        allow = map_daily_to_h1(h1, allow_d.astype(float)) > 0.5
        m = backtest(h1, p, ifvg_ok=bear & allow, start_i=0, collect_trades=False)
        fmt(m, label, allow)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
