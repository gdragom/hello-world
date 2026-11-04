#!/usr/bin/env python3
"""Compare TV Long Custom (Deep 2019-07-10 → now) vs Python ledger_engine."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ledger_engine import Params, backtest
from parity_tv_last365 import bull_ifvg_ok, load_csv

H1 = ROOT / "data" / "btcusdt_1h_bitget.csv"
M5 = ROOT / "data" / "btcusdt_5m_bitget.csv"

# Decoded from TV v0.9.7 Long status + tester: Jul 10 2019 – Oct 5 2026 Deep
P = Params(
    swing_len=8,
    min_swing_atr=0.6,
    atr_len=14,
    fib_mode="immediate",
    entry_mode="zone_fvg_ob",
    bias_filter="aligned",
    short_filter="long_only",
    rr_mult=2.0,
    sl_mode="fixed_usd",
    fixed_usd_sl=500.0,
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
    fixed_tp_usd=1000.0,
    fixed_risk_usd=500.0,
    allow_long=True,
)


def main() -> int:
    h1 = load_csv(H1)
    m5 = load_csv(M5)
    print(f"H1 {len(h1)} {h1.index.min()} .. {h1.index.max()}", flush=True)
    print(f"M5 {len(m5)} {m5.index.min()} .. {m5.index.max()}", flush=True)
    ifvg = bull_ifvg_ok(h1, m5, 6)
    m = backtest(h1, P, ifvg_ok=ifvg, start_i=0)
    tv = dict(trades=197, wins=83, wr=42.13, pf=1.329, pnl=19967.76, pnl_pct=199.68, max_dd=6410.80, max_dd_pct=38.78)
    print("---", flush=True)
    print(
        f"PY  n={m.trades} wins={m.wins} WR={m.wr:.2f}% PF={m.pf:.3f} "
        f"PnL={m.pnl:.1f} ({m.pnl_pct:.2f}%) DD={m.max_dd:.1f} ({m.max_dd_pct:.2f}%)",
        flush=True,
    )
    print(
        f"TV  n={tv['trades']} wins={tv['wins']} WR={tv['wr']:.2f}% PF={tv['pf']:.3f} "
        f"PnL={tv['pnl']:.1f} ({tv['pnl_pct']:.2f}%) DD={tv['max_dd']:.1f} ({tv['max_dd_pct']:.2f}%)",
        flush=True,
    )
    print(
        f"dN={m.trades - tv['trades']} dWR={m.wr - tv['wr']:+.2f} dPF={m.pf - tv['pf']:+.3f} "
        f"dPnL%={m.pnl_pct - tv['pnl_pct']:+.2f} dDD%={m.max_dd_pct - tv['max_dd_pct']:+.2f}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
