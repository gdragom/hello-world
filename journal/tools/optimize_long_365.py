#!/usr/bin/env python3
"""
Long v0.9.4-style grid on Bitget BTCUSDT 1H + 5m IFVG.

Fixed book: $500 SL / $1000 TP / $500 risk, long only, 5m bullish IFVG.
Varies the Custom knobs: bias, wick vs close, swing, ATR, fib, entry, cooldowns.

Rank is approximate (engine is not bit-identical to TradingView). Confirm winners on TV.
"""
from __future__ import annotations

import itertools
import json
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ledger_engine import Params, backtest  # noqa: E402

H1_CACHE = ROOT / "data" / "btcusdt_1h_bitget.csv"
M5_CACHE = ROOT / "data" / "btcusdt_5m_bitget.csv"
OUT_CSV = ROOT / "out" / "long_365_grid.csv"


def fetch_bitget(granularity: str, start: datetime, end: datetime) -> pd.DataFrame:
    """Public Bitget USDT-M history candles, walking backward from end."""
    end_ms = int(end.timestamp() * 1000)
    start_ms = int(start.timestamp() * 1000)
    rows: dict[int, list[float]] = {}
    guard = 0
    while end_ms > start_ms and guard < 800:
        guard += 1
        url = (
            "https://api.bitget.com/api/v2/mix/market/history-candles"
            f"?symbol=BTCUSDT&productType=USDT-FUTURES&granularity={granularity}"
            f"&endTime={end_ms}&limit=200"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "ledger-opt/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode())
        data = payload.get("data") or []
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
        nxt = oldest - 1
        if nxt >= end_ms:
            break
        end_ms = nxt
        if guard == 1 or guard % 25 == 0:
            print(f"  {granularity} page {guard} bars {len(rows)}", flush=True)
    if not rows:
        raise RuntimeError(f"Bitget returned no {granularity} candles")
    idx = pd.to_datetime(sorted(rows), unit="ms", utc=True)
    arr = [rows[int(t.value // 1_000_000)] for t in idx]
    df = pd.DataFrame(arr, index=idx, columns=["open", "high", "low", "close"])
    return df.sort_index()


def load_or_fetch(path: Path, granularity: str, start: datetime, end: datetime) -> pd.DataFrame:
    if path.exists():
        df = pd.read_csv(path)
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
        df = df.set_index("ts").sort_index()
        if df.index.min() <= pd.Timestamp(start) and df.index.max() >= pd.Timestamp(end) - pd.Timedelta(days=2):
            print(f"cache {path.name} {len(df)} bars {df.index.min()} -> {df.index.max()}")
            return df[["open", "high", "low", "close"]].astype(float)
    print(f"fetch Bitget {granularity} ...")
    df = fetch_bitget(granularity, start, end)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    out.insert(0, "ts", out.index)
    out.to_csv(path, index=False)
    print(f"wrote {len(df)} -> {path}")
    return df


def bull_ifvg_on_1h(h1: pd.DataFrame, m5: pd.DataFrame, max_age: int = 12) -> np.ndarray:
    """True on a 1H bar when the 5m bullish IFVG age at that close is <= max_age."""
    low = m5["low"].to_numpy()
    high = m5["high"].to_numpy()
    close = m5["close"].to_numpy()
    n = len(m5)
    age = np.full(n, 10_000, dtype=int)
    last_top = np.nan
    last_inv = -10_000
    for i in range(n):
        if i >= 2 and low[i - 2] > high[i]:
            last_top = low[i - 2]
        if not np.isnan(last_top) and close[i] > last_top and (i == 0 or close[i - 1] <= last_top):
            last_inv = i
        if last_inv >= 0:
            age[i] = i - last_inv
    m5_ns = m5.index.asi8
    h1_ns = h1.index.asi8
    # last 5m bar at or before each 1H timestamp
    pos = np.searchsorted(m5_ns, h1_ns, side="right") - 1
    ok = np.zeros(len(h1), dtype=bool)
    valid = pos >= 0
    ok[valid] = age[pos[valid]] <= max_age
    return ok


def combos() -> list[Params]:
    """Custom-panel knobs. Cooldown and post-stop move together (0 or 2)."""
    out = []
    for bias, wick, swing, atr, fib, cool in itertools.product(
        ["off", "block_opp", "aligned"],
        [False, True],
        [6, 8, 10],
        [0.45, 0.6, 0.8],
        ["immediate", "wait"],
        [0, 2],
    ):
        out.append(
            Params(
                swing_len=swing,
                min_swing_atr=atr,
                fib_mode=fib,  # type: ignore
                entry_mode="zone_only",
                bias_filter=bias,  # type: ignore
                short_filter="long_only",
                rr_mult=2.0,
                sl_mode="fixed_usd",
                fixed_usd_sl=500.0,
                reenter=True,
                cooldown=cool,
                post_stop_cooldown=cool,
                lock_fib_on_stop=False,
                min_hold_bars=0,
                be_trigger_r=0.0,
                eq_wick=wick,
                use_fixed_dollar=True,
                fixed_tp_usd=1000.0,
                fixed_risk_usd=500.0,
            )
        )
    return out


def main() -> int:
    end = datetime.now(timezone.utc)
    entry_from = end - timedelta(days=365)
    fetch_from = entry_from - timedelta(days=120)
    h1 = load_or_fetch(H1_CACHE, "1H", fetch_from, end)
    m5 = load_or_fetch(M5_CACHE, "5m", fetch_from, end)
    h1 = h1.loc[h1.index >= pd.Timestamp(fetch_from)]
    m5 = m5.loc[m5.index >= pd.Timestamp(fetch_from)]
    ifvg = bull_ifvg_on_1h(h1, m5, 12)
    start_i = int(np.searchsorted(h1.index.asi8, pd.Timestamp(entry_from).value, side="left"))
    print(
        f"1H {len(h1)} 5m {len(m5)} entry_from {entry_from.date()} start_i {start_i} "
        f"ifvg_true {int(ifvg[start_i:].sum())}"
    )
    grid = combos()
    print(f"grid {len(grid)}")
    rows = []
    t0 = time.time()
    for i, p in enumerate(grid, 1):
        m = backtest(h1, p, ifvg_ok=ifvg, start_i=start_i)
        rows.append(
            {
                "bias": p.bias_filter,
                "wick": p.eq_wick,
                "swing": p.swing_len,
                "min_atr": p.min_swing_atr,
                "fib": p.fib_mode,
                "entry": p.entry_mode,
                "cool": p.cooldown,
                "post_stop": p.post_stop_cooldown,
                "trades": m.trades,
                "wr": round(m.wr, 2),
                "pf": round(m.pf, 3),
                "pnl": round(m.pnl, 1),
                "pnl_pct": round(m.pnl_pct, 2),
                "max_dd_pct": round(m.max_dd_pct, 2),
            }
        )
        if i % 40 == 0 or i == len(grid):
            elapsed = time.time() - t0
            print(f"  {i}/{len(grid)} {elapsed:.0f}s")
    df = pd.DataFrame(rows)
    df = df[df["trades"] >= 20].copy()
    df["rank_pf"] = df["pf"].rank(ascending=False, method="min")
    df["rank_wr"] = df["wr"].rank(ascending=False, method="min")
    df = df.sort_values(["pf", "wr", "pnl"], ascending=False)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_CSV, index=False)
    print(f"\nWrote {OUT_CSV} rows={len(df)}")
    print("\n=== TOP 12 BY PF (min 20 trades) ===")
    print(df.head(12).to_string(index=False))
    print("\n=== TOP 8 BY WIN RATE ===")
    print(df.sort_values(["wr", "pf"], ascending=False).head(8).to_string(index=False))
    base = df[
        (df.swing == 8)
        & (df.min_atr == 0.6)
        & (df.fib == "immediate")
        & (df.entry == "zone_only")
        & (df.cool == 2)
        & (df.post_stop == 2)
    ]
    print("\n=== YOUR CUSTOM STACK (swing 8 / 0.6 / immediate / zone only / cool 2) ===")
    if len(base):
        print(base.sort_values("bias").to_string(index=False))
    else:
        print("no rows (fewer than 20 trades)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
