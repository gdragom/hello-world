#!/usr/bin/env python3
"""Build parity viz JSON: 1H candles + Python fib/FVG/entries + TV entries (2026→now)."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from diff_tv_python_long365 import parse_tv  # noqa: E402
from ledger_engine import backtest  # noqa: E402
from parity_tv_last365 import bull_ifvg_ok, load_csv, tv_params  # noqa: E402

OUT = Path(__file__).resolve().parent / "data.json"
H1 = ROOT / "data" / "btcusdt_1h_bitget.csv"
M1 = ROOT / "data" / "btcusdt_1m_bitget.csv"
TV_CSV = ROOT / "out" / "tv_long_365_20260920.csv"

VIZ_START = pd.Timestamp("2026-01-01", tz="UTC")
WARM_DAYS = 60


def _iso(ts) -> str:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    else:
        t = t.tz_convert("UTC")
    return t.isoformat().replace("+00:00", "Z")


def main() -> int:
    end = datetime.now(timezone.utc)
    warm = VIZ_START - pd.Timedelta(days=WARM_DAYS)

    h1_all = load_csv(H1)
    h1 = h1_all.loc[h1_all.index >= warm].copy()
    start_i = int(np.searchsorted(h1.index.asi8, VIZ_START.value, side="left"))
    print(f"H1 bars={len(h1)} start_i={start_i} from {h1.index[0]}", flush=True)

    m1 = load_csv(M1)
    ifvg1 = bull_ifvg_ok(h1, m1, 12)
    p = tv_params(entry_mode="zone_fvg_ob", eq_wick=True)
    m = backtest(
        h1,
        p,
        ifvg_ok=ifvg1,
        start_i=start_i,
        collect_trades=True,
        collect_trace=True,
    )
    trace = getattr(m, "trace", None) or {"fibs": [], "fvgs": [], "bos": []}
    trades = getattr(m, "trade_log", None) or []

    # Candles from 2026 only (structure was warmed before)
    h1_viz = h1.loc[h1.index >= VIZ_START]
    candles = []
    for ts, row in h1_viz.iterrows():
        candles.append(
            {
                "time": _iso(ts),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
            }
        )

    def in_viz(t: str) -> bool:
        return pd.Timestamp(t) >= VIZ_START

    py_entries = []
    for t in trades:
        if not in_viz(t["entry_time"]):
            continue
        py_entries.append(
            {
                "time": _iso(t["entry_time"]),
                "exit_time": _iso(t["exit_time"]),
                "price": float(t["entry_px"]),
                "exit_price": float(t["exit_px"]),
                "pnl": float(t["pnl"]),
                "side": t["side"],
            }
        )

    tv_entries = []
    if TV_CSV.exists():
        tv = parse_tv(TV_CSV)
        for _, r in tv.iterrows():
            if r["entry_time"] < VIZ_START:
                continue
            tv_entries.append(
                {
                    "time": _iso(r["entry_time"]),
                    "exit_time": _iso(r["exit_time"]) if pd.notna(r["exit_time"]) else None,
                    "price": float(r["entry_px"]),
                    "pnl": float(r["pnl"]),
                    "side": "long",
                }
            )

    fibs = []
    for f in trace.get("fibs", []):
        if not in_viz(f["t0"]) and not in_viz(f.get("t1", f["t0"])):
            # keep if segment overlaps viz window
            t1 = pd.Timestamp(f.get("t1", f["t0"]))
            if t1 < VIZ_START:
                continue
        t0 = max(pd.Timestamp(f["t0"]), VIZ_START)
        fibs.append(
            {
                "t0": _iso(t0),
                "t1": _iso(f["t1"]),
                "eq": f["eq"],
                "lo": f["lo"],
                "hi": f["hi"],
                "side": f.get("side", "long"),
            }
        )

    fvgs = []
    for z in trace.get("fvgs", []):
        t1 = pd.Timestamp(z.get("t1", z["t0"]))
        if t1 < VIZ_START:
            continue
        t0 = max(pd.Timestamp(z["t0"]), VIZ_START)
        fvgs.append(
            {
                "t0": _iso(t0),
                "t1": _iso(z["t1"]),
                "top": z["top"],
                "bot": z["bot"],
                "side": z.get("side", "long"),
            }
        )

    bos = []
    for b in trace.get("bos", []):
        if not in_viz(b["time"]):
            continue
        bos.append({"time": _iso(b["time"]), "level": b["level"], "side": b.get("side", "long")})

    # Match entry hours
    py_h = {pd.Timestamp(e["time"]).floor("h") for e in py_entries}
    tv_h = {pd.Timestamp(e["time"]).floor("h") for e in tv_entries}
    both = len(py_h & tv_h)

    payload = {
        "meta": {
            "symbol": "BTCUSDT.P Bitget",
            "tf": "1H",
            "from": _iso(VIZ_START),
            "to": _iso(end),
            "config": "Custom Aligned swing8 0.6 Immediate Zone+FVG/OB cool10 Wick 1mIFVG12 $500/$1000",
            "generated_at": _iso(end),
            "note": "Fib/FVG overlays from Python. Entries: TV export vs Python (synced after IFVG bar-close map). Refresh page after rebuild.",
        },
        "stats": {
            "candles": len(candles),
            "py_trades": len(py_entries),
            "tv_trades": len(tv_entries),
            "matched_entry_hours": both,
            "py_wr": round(m.wr, 2),
            "py_pf": round(m.pf, 3),
            "py_pnl_pct": round(m.pnl_pct, 2),
            "fib_segments": len(fibs),
            "fvg_boxes": len(fvgs),
        },
        "candles": candles,
        "fibs": fibs,
        "fvgs": fvgs,
        "bos": bos,
        "py_entries": py_entries,
        "tv_entries": tv_entries,
    }
    OUT.write_text(json.dumps(payload), encoding="utf-8")
    print(
        f"Wrote {OUT} candles={len(candles)} py={len(py_entries)} tv={len(tv_entries)} "
        f"fibs={len(fibs)} fvgs={len(fvgs)} match_h={both}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
