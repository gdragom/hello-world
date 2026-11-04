#!/usr/bin/env python3
"""Diff exported TV List of Trades vs Python replay (screenshot Custom config)."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, ROOT)

from ledger_engine import Params, backtest  # noqa: E402
from parity_tv_last365 import bull_ifvg_ok, load_csv, tv_params  # noqa: E402

H1 = ROOT / "data" / "btcusdt_1h_bitget.csv"
M1 = ROOT / "data" / "btcusdt_1m_bitget.csv"
TV_CSV = ROOT / "out" / "tv_long_365_20260920.csv"


def parse_tv(path: Path, chart_tz: str = "America/New_York") -> pd.DataFrame:
    """Parse TV List of Trades. Times are chart timezone (usually exchange/NY), not UTC."""
    raw = pd.read_csv(path)
    # TV exports Exit then Entry per trade#; keep Entry long rows
    ent = raw[raw["Type"].astype(str).str.lower() == "entry long"].copy()
    ent["entry_time"] = (
        pd.to_datetime(ent["Date and time"])
        .dt.tz_localize(chart_tz, ambiguous="infer", nonexistent="shift_forward")
        .dt.tz_convert("UTC")
    )
    exits = raw[raw["Type"].astype(str).str.lower() == "exit long"].copy()
    exits["exit_time"] = (
        pd.to_datetime(exits["Date and time"])
        .dt.tz_localize(chart_tz, ambiguous="infer", nonexistent="shift_forward")
        .dt.tz_convert("UTC")
    )
    exits = exits.set_index("Trade number")
    ent["exit_time"] = ent["Trade number"].map(exits["exit_time"])
    ent["pnl"] = pd.to_numeric(ent["Net PnL USDT"], errors="coerce")
    ent["entry_px"] = pd.to_numeric(ent["Price USDT"], errors="coerce")
    ent = ent.sort_values("entry_time").reset_index(drop=True)
    return ent[["Trade number", "entry_time", "exit_time", "entry_px", "pnl"]]


def tv_metrics(ent: pd.DataFrame) -> dict:
    pnls = ent["pnl"].astype(float).tolist()
    trades = len(pnls)
    wins = sum(1 for x in pnls if x > 0)
    gw = sum(x for x in pnls if x > 0)
    gl = abs(sum(x for x in pnls if x <= 0))
    pf = gw / gl if gl > 0 else (99.0 if wins else 0.0)
    pnl = sum(pnls)
    return {
        "trades": trades,
        "wins": wins,
        "wr": round(100.0 * wins / trades, 2) if trades else 0.0,
        "pf": round(pf, 3),
        "pnl": round(pnl, 2),
        "pnl_pct": round(100.0 * pnl / 10_000.0, 2),
    }


def main() -> int:
    if not TV_CSV.exists():
        print(f"Missing TV export: {TV_CSV}")
        return 1

    tv = parse_tv(TV_CSV)
    tv_m = tv_metrics(tv)
    print("TV export:", TV_CSV.name)
    print(
        f"  n={tv_m['trades']} WR={tv_m['wr']}% PF={tv_m['pf']} "
        f"PnL={tv_m['pnl']} ({tv_m['pnl_pct']}%)",
        flush=True,
    )
    print(f"  first={tv['entry_time'].iloc[0]} last={tv['entry_time'].iloc[-1]}", flush=True)

    end = datetime.now(timezone.utc)
    entry_from = end - timedelta(days=365)
    warm = entry_from - timedelta(days=60)

    h1 = load_csv(H1)
    h1 = h1.loc[h1.index >= pd.Timestamp(warm)]
    start_i = int(np.searchsorted(h1.index.asi8, pd.Timestamp(entry_from).value, side="left"))
    m1 = load_csv(M1)
    ifvg1 = bull_ifvg_ok(h1, m1, 12)

    p = tv_params(entry_mode="zone_fvg_ob", eq_wick=True)
    m = backtest(h1, p, ifvg_ok=ifvg1, start_i=start_i, collect_trades=True)
    py = getattr(m, "trade_log", []) or []
    py_ent = pd.DataFrame(py)
    if len(py_ent):
        py_ent["entry_time"] = pd.to_datetime(py_ent["entry_time"], utc=True)
        py_ent = py_ent.sort_values("entry_time").reset_index(drop=True)

    print(
        f"PY screenshot: n={m.trades} WR={m.wr:.2f}% PF={m.pf:.3f} "
        f"PnL={m.pnl:.1f} ({m.pnl_pct:.2f}%) DD={m.max_dd_pct:.1f}%",
        flush=True,
    )

    tv_times = set(tv["entry_time"].dt.floor("h"))
    py_times = set(py_ent["entry_time"].dt.floor("h")) if len(py_ent) else set()
    both = sorted(tv_times & py_times)
    only_tv = sorted(tv_times - py_times)
    only_py = sorted(py_times - tv_times)

    print("\n=== entry-time match (floored to hour, UTC) ===", flush=True)
    print(f"  both={len(both)}  TV-only={len(only_tv)}  PY-only={len(only_py)}", flush=True)
    print(f"  overlap={100.0 * len(both) / max(len(tv_times), 1):.1f}% of TV entries", flush=True)

    def show(label: str, times: list, limit: int = 12) -> None:
        print(f"\n{label} ({len(times)}):", flush=True)
        for t in times[:limit]:
            print(f"  {t}", flush=True)
        if len(times) > limit:
            print(f"  ... +{len(times) - limit} more", flush=True)

    show("TV-only entries", only_tv)
    show("PY-only entries", only_py)
    show("Matched entries", both, limit=8)

    entries_synced = len(only_tv) == 0 and len(only_py) == 0 and m.trades == tv_m["trades"]
    metrics_close = (
        abs(m.pf - tv_m["pf"]) < 0.05
        and abs(m.wr - tv_m["wr"]) < 1.0
        and abs(m.pnl_pct - tv_m["pnl_pct"]) < 2.0
    )
    same = bool(entries_synced and metrics_close)
    print("\n=== verdict ===", flush=True)
    if same:
        print("SAME — trade list and summary metrics match TV.", flush=True)
    elif entries_synced:
        print(
            "ENTRIES SYNCED (100% hour match) — PnL/PF still differ slightly "
            "(exit fill / commission edge cases).",
            flush=True,
        )
        print(
            f"  delta trades={m.trades - tv_m['trades']:+d} "
            f"dWR={m.wr - tv_m['wr']:+.1f} dPF={m.pf - tv_m['pf']:+.3f} "
            f"dPnL%={m.pnl_pct - tv_m['pnl_pct']:+.1f}",
            flush=True,
        )
    else:
        print(
            "NOT THE SAME — Python does not reproduce this TV last-365 trade list "
            "under the attached Custom screenshot config.",
            flush=True,
        )
        print(
            f"  delta trades={m.trades - tv_m['trades']:+d} "
            f"dWR={m.wr - tv_m['wr']:+.1f} dPF={m.pf - tv_m['pf']:+.3f} "
            f"dPnL%={m.pnl_pct - tv_m['pnl_pct']:+.1f}",
            flush=True,
        )

    out = {
        "tv": tv_m,
        "python": {
            "trades": int(m.trades),
            "wr": round(float(m.wr), 2),
            "pf": round(float(m.pf), 3),
            "pnl": round(float(m.pnl), 2),
            "pnl_pct": round(float(m.pnl_pct), 2),
            "max_dd_pct": round(float(m.max_dd_pct), 2),
        },
        "match": {
            "both": int(len(both)),
            "tv_only": int(len(only_tv)),
            "py_only": int(len(only_py)),
            "entries_synced": bool(entries_synced),
            "same": bool(same),
        },
        "tv_only_entries": [str(t) for t in only_tv],
        "py_only_entries": [str(t) for t in only_py],
        "config": "Custom Aligned swing8 0.6 Immediate Zone+FVG/OB cool10 Wick 1mIFVG12 $500/$1000",
    }
    out_path = ROOT / "out" / "diff_tv_python_long365.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nWrote {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
