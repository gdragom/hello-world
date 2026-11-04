#!/usr/bin/env python3
"""Download Bitget 1m BTCUSDT with resume + 429 backoff, then parity vs TV."""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ledger_engine import Params, backtest  # noqa: E402
from parity_tv_last365 import TV_REF, bull_ifvg_ok, load_csv, report, tv_params  # noqa: E402

H1 = ROOT / "data" / "btcusdt_1h_bitget.csv"
M5 = ROOT / "data" / "btcusdt_5m_bitget.csv"
M1 = ROOT / "data" / "btcusdt_1m_bitget.csv"


def fetch_page(granularity: str, end_ms: int) -> list:
    url = (
        "https://api.bitget.com/api/v2/mix/market/history-candles"
        f"?symbol=BTCUSDT&productType=USDT-FUTURES&granularity={granularity}"
        f"&endTime={end_ms}&limit=200"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "ledger-parity/1.1"})
    for attempt in range(8):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode())
            return payload.get("data") or []
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
            wait = min(60, 2 ** attempt)
            print(f"  429 backoff {wait}s", flush=True)
            time.sleep(wait)
    return []


def resume_fetch_1m(start: datetime, end: datetime) -> pd.DataFrame:
    rows: dict[int, list[float]] = {}
    if M1.exists():
        old = load_csv(M1)
        for ts, row in old.iterrows():
            rows[int(ts.value // 1_000_000)] = [row.open, row.high, row.low, row.close]
        print(f"resume from cache bars={len(rows)}", flush=True)

    end_ms = int(end.timestamp() * 1000)
    start_ms = int(start.timestamp() * 1000)
    if rows:
        # continue older than oldest cached
        end_ms = min(end_ms, min(rows.keys()) - 1)

    guard = 0
    while end_ms > start_ms and guard < 6000:
        guard += 1
        data = fetch_page("1m", end_ms)
        if not data:
            break
        oldest = None
        for row in data:
            ts = int(row[0])
            if ts < start_ms:
                continue
            rows[ts] = [float(row[1]), float(row[2]), float(row[3]), float(row[4])]
            oldest = ts if oldest is None else min(oldest, ts)
        if oldest is None or len(data) < 200:
            break
        end_ms = oldest - 1
        if guard % 25 == 0:
            # checkpoint
            idx = pd.to_datetime(sorted(rows), unit="ms", utc=True)
            arr = [rows[int(t.value // 1_000_000)] for t in idx]
            df = pd.DataFrame(arr, index=idx, columns=["open", "high", "low", "close"])
            out = df.copy()
            out.insert(0, "ts", out.index)
            out.to_csv(M1, index=False)
            print(f"  1m page {guard} bars={len(rows)} oldest={df.index.min()}", flush=True)
        time.sleep(0.08)

    idx = pd.to_datetime(sorted(rows), unit="ms", utc=True)
    arr = [rows[int(t.value // 1_000_000)] for t in idx]
    df = pd.DataFrame(arr, index=idx, columns=["open", "high", "low", "close"]).sort_index()
    out = df.copy()
    out.insert(0, "ts", out.index)
    out.to_csv(M1, index=False)
    print(f"1m done bars={len(df)} {df.index.min()} -> {df.index.max()}", flush=True)
    return df


def main() -> int:
    end = datetime.now(timezone.utc)
    entry_from = end - timedelta(days=365)
    warm = entry_from - timedelta(days=60)

    h1 = load_csv(H1)
    h1 = h1.loc[h1.index >= pd.Timestamp(warm)]
    start_i = int(np.searchsorted(h1.index.asi8, pd.Timestamp(entry_from).value, side="left"))
    print(f"H1={len(h1)} start_i={start_i} entry_from={entry_from.date()}", flush=True)

    print("fetch/resume 1m...", flush=True)
    m1 = resume_fetch_1m(warm, end)
    # need coverage through entry window
    if m1.index.min() > pd.Timestamp(entry_from):
        print("WARNING: 1m still incomplete for full entry window", flush=True)

    ifvg1 = bull_ifvg_ok(h1, m1, 12)
    print(f"1m IFVG hits in entry window: {int(ifvg1[start_i:].sum())}", flush=True)

    results = []
    p = tv_params(entry_mode="zone_fvg_ob", eq_wick=True)
    m = backtest(h1, p, ifvg_ok=ifvg1, start_i=start_i)
    results.append(report("PY screenshot (Zone+FVG/OB wick 1m)", m))

    p2 = tv_params(entry_mode="zone_only", eq_wick=True)
    m = backtest(h1, p2, ifvg_ok=ifvg1, start_i=start_i)
    results.append(report("PY Zone-only wick 1m", m))

    if M5.exists():
        m5 = load_csv(M5)
        m5 = m5.loc[m5.index >= pd.Timestamp(warm)]
        ifvg5 = bull_ifvg_ok(h1, m5, 12)
        m = backtest(h1, p, ifvg_ok=ifvg5, start_i=start_i)
        results.append(report("PY screenshot knobs but 5m IFVG", m))

    print("\n=== vs TV ===", flush=True)
    print(
        f"TV  n={TV_REF['trades']} WR={TV_REF['wr']}% PF={TV_REF['pf']} "
        f"PnL%={TV_REF['pnl_pct']} DD={TV_REF['max_dd_pct']}",
        flush=True,
    )
    out = ROOT / "out" / "parity_tv_last365.json"
    out.write_text(json.dumps({"tv": TV_REF, "python": results}, indent=2), encoding="utf-8")
    print(f"Wrote {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
