#!/usr/bin/env python3
"""Parity check: TV Custom screenshot config vs Python last-365."""
from __future__ import annotations

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

H1 = ROOT / "data" / "btcusdt_1h_bitget.csv"
M5 = ROOT / "data" / "btcusdt_5m_bitget.csv"
M1 = ROOT / "data" / "btcusdt_1m_bitget.csv"

# From user's TV screenshot (LEDGER ICT 1H LONG v0.9.4 Custom)
TV_REF = {
    "trades": 36,
    "wins": 17,
    "wr": 47.22,
    "pf": 1.622,
    "pnl": 6310.40,
    "pnl_pct": 63.10,
    "max_dd_pct": 20.69,
}


def fetch_bitget(granularity: str, start: datetime, end: datetime, max_pages: int = 3000) -> pd.DataFrame:
    end_ms = int(end.timestamp() * 1000)
    start_ms = int(start.timestamp() * 1000)
    rows: dict[int, list[float]] = {}
    guard = 0
    while end_ms > start_ms and guard < max_pages:
        guard += 1
        url = (
            "https://api.bitget.com/api/v2/mix/market/history-candles"
            f"?symbol=BTCUSDT&productType=USDT-FUTURES&granularity={granularity}"
            f"&endTime={end_ms}&limit=200"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "ledger-parity/1.0"})
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
        time.sleep(0.02)
        if guard == 1 or guard % 50 == 0:
            print(f"  {granularity} page {guard} bars={len(rows)}", flush=True)
    if not rows:
        raise RuntimeError(f"no {granularity} data")
    idx = pd.to_datetime(sorted(rows), unit="ms", utc=True)
    arr = [rows[int(t.value // 1_000_000)] for t in idx]
    return pd.DataFrame(arr, index=idx, columns=["open", "high", "low", "close"]).sort_index()


def load_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df.set_index("ts").sort_index()[["open", "high", "low", "close"]].astype(float)


def ensure_h1(start: datetime, end: datetime) -> pd.DataFrame:
    if H1.exists():
        df = load_csv(H1)
        if df.index.min() <= pd.Timestamp(start) and df.index.max() >= pd.Timestamp(end) - pd.Timedelta(days=3):
            print(f"H1 cache {len(df)} {df.index.min()} -> {df.index.max()}")
            return df
    print("fetch H1...")
    df = fetch_bitget("1H", start, end, max_pages=200)
    out = df.copy()
    out.insert(0, "ts", out.index)
    H1.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(H1, index=False)
    return df


def bull_ifvg_ok(
    h1: pd.DataFrame,
    ltf: pd.DataFrame,
    max_age: int,
    *,
    htf_minutes: int = 60,
) -> np.ndarray:
    """Map LTF bullish IFVG age onto HTF bars — Pine request.security at HTF close.

    age = bars since inversion (bearish FVG then close above its top).
    HTF evaluation uses the last LTF bar at/before HTF bar close (lookahead_off).
    """
    low = ltf["low"].to_numpy()
    high = ltf["high"].to_numpy()
    close = ltf["close"].to_numpy()
    n = len(ltf)
    age = np.full(n, 10_000, dtype=int)
    last_top = np.nan
    last_inv = -10_000
    for i in range(n):
        # Pine: bearFvg = low[2] > high[0]; lastTop = valuewhen(..., low[2])
        if i >= 2 and low[i - 2] > high[i]:
            last_top = low[i - 2]
        if not np.isnan(last_top) and close[i] > last_top and (i == 0 or close[i - 1] <= last_top):
            last_inv = i
        if last_inv >= 0:
            age[i] = i - last_inv
    # Bar-close: HTF open + period; last LTF open strictly before HTF close
    htf_close = h1.index + pd.Timedelta(minutes=htf_minutes)
    pos = np.searchsorted(ltf.index.asi8, htf_close.asi8, side="left") - 1
    ok = np.zeros(len(h1), dtype=bool)
    valid = pos >= 0
    ok[valid] = age[pos[valid]] <= max_age
    return ok


def tv_params(*, entry_mode: str, eq_wick: bool) -> Params:
    return Params(
        swing_len=8,
        min_swing_atr=0.6,
        atr_len=14,
        fib_mode="immediate",
        entry_mode=entry_mode,  # type: ignore
        bias_filter="aligned",
        short_filter="long_only",
        rr_mult=2.0,
        sl_mode="fixed_usd",
        fixed_usd_sl=500.0,
        zone_keep=80,
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
        eq_wick=eq_wick,
        use_fixed_dollar=True,
        fixed_tp_usd=1000.0,
        fixed_risk_usd=500.0,
    )


def report(label: str, m) -> dict:
    row = {
        "label": label,
        "trades": m.trades,
        "wr": round(m.wr, 2),
        "pf": round(m.pf, 3),
        "pnl": round(m.pnl, 1),
        "pnl_pct": round(m.pnl_pct, 2),
        "max_dd_pct": round(m.max_dd_pct, 2),
    }
    print(
        f"{label:42s} n={m.trades:3d} WR={m.wr:5.1f}% PF={m.pf:5.3f} "
        f"PnL={m.pnl:8.1f} ({m.pnl_pct:6.2f}%) DD={m.max_dd_pct:5.1f}%",
        flush=True,
    )
    return row


def main() -> int:
    end = datetime.now(timezone.utc)
    entry_from = end - timedelta(days=365)
    warm = entry_from - timedelta(days=60)
    print("TV ref (your last-365 Deep report):", TV_REF, flush=True)
    print(
        "Screenshot config: Custom · Aligned · Any · swing8 · 0.6ATR · Immediate · "
        "Zone+FVG/OB · cool10/post10 · Wick · IFVG on · LTF=1m age12 · $500/$1000",
        flush=True,
    )

    h1 = ensure_h1(warm, end)
    h1 = h1.loc[h1.index >= pd.Timestamp(warm)]
    start_i = int(np.searchsorted(h1.index.asi8, pd.Timestamp(entry_from).value, side="left"))
    print(f"H1 bars={len(h1)} entry_from={entry_from.date()} start_i={start_i}", flush=True)

    m5 = load_csv(M5) if M5.exists() else None
    if m5 is not None:
        m5 = m5.loc[m5.index >= pd.Timestamp(warm)]
        print(f"M5 bars={len(m5)}", flush=True)

    # 1m: fetch if missing / short (TV uses 1m)
    m1 = None
    need_m1_start = entry_from - timedelta(days=5)
    if M1.exists():
        m1 = load_csv(M1)
        if m1.index.min() > pd.Timestamp(need_m1_start) or m1.index.max() < pd.Timestamp(end) - pd.Timedelta(days=2):
            print("1m cache incomplete — refetch...", flush=True)
            m1 = None
        else:
            print(f"M1 cache {len(m1)} {m1.index.min()} -> {m1.index.max()}", flush=True)
    if m1 is None:
        print("fetch Bitget 1m from warm start (slow)...", flush=True)
        try:
            m1 = fetch_bitget("1m", warm, end, max_pages=5000)
            out = m1.copy()
            out.insert(0, "ts", out.index)
            out.to_csv(M1, index=False)
            print(f"wrote 1m {len(m1)} -> {M1}", flush=True)
        except Exception as exc:
            print(f"1m fetch failed: {exc}", flush=True)
            m1 = None

    results = []
    # Exact screenshot: zone_fvg_ob + wick + aligned + cool10
    p = tv_params(entry_mode="zone_fvg_ob", eq_wick=True)

    if m1 is not None and len(m1) > 1000:
        ifvg1 = bull_ifvg_ok(h1, m1, 12)
        print(f"1m IFVG true on entry window: {int(ifvg1[start_i:].sum())}", flush=True)
        m = backtest(h1, p, ifvg_ok=ifvg1, start_i=start_i)
        results.append(report("PY screenshot (1m IFVG)", m))
    else:
        print("SKIP 1m IFVG run (no 1m data)", flush=True)

    if m5 is not None:
        ifvg5 = bull_ifvg_ok(h1, m5, 12)
        m = backtest(h1, p, ifvg_ok=ifvg5, start_i=start_i)
        results.append(report("PY same knobs but 5m IFVG", m))

    # Also zone_only (in case truncated dropdown was Zone only)
    p2 = tv_params(entry_mode="zone_only", eq_wick=True)
    if m1 is not None and len(m1) > 1000:
        ifvg1 = bull_ifvg_ok(h1, m1, 12)
        m = backtest(h1, p2, ifvg_ok=ifvg1, start_i=start_i)
        results.append(report("PY Zone-only + wick + 1m IFVG", m))
    if m5 is not None:
        ifvg5 = bull_ifvg_ok(h1, m5, 12)
        m = backtest(h1, p2, ifvg_ok=ifvg5, start_i=start_i)
        results.append(report("PY Zone-only + wick + 5m IFVG", m))

    print("\n=== vs TV ===", flush=True)
    print(
        f"{'TV last-365 Deep':42s} n={TV_REF['trades']:3d} WR={TV_REF['wr']:5.1f}% "
        f"PF={TV_REF['pf']:5.3f} PnL={TV_REF['pnl']:8.1f} ({TV_REF['pnl_pct']:6.2f}%) "
        f"DD={TV_REF['max_dd_pct']:5.1f}%",
        flush=True,
    )
    for r in results:
        dt = r["trades"] - TV_REF["trades"]
        dpf = r["pf"] - TV_REF["pf"]
        dwr = r["wr"] - TV_REF["wr"]
        dpnl = r["pnl_pct"] - TV_REF["pnl_pct"]
        print(
            f"  delta {r['label'][:36]:36s} dn={dt:+4d} dWR={dwr:+6.1f} dPF={dpf:+6.3f} dPnL%={dpnl:+6.1f}",
            flush=True,
        )

    out = ROOT / "out" / "parity_tv_last365.json"
    out.write_text(json.dumps({"tv": TV_REF, "python": results}, indent=2), encoding="utf-8")
    print(f"\nWrote {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
