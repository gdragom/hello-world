#!/usr/bin/env python3
"""Fetch Bitget XAUUSDT 1H + 5m candles into data/xauusdt_*_bitget.csv (resumable)."""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from parity_tv_last365 import load_csv

DATA = Path(__file__).resolve().parent / "data"
FILES = {"1H": DATA / "xauusdt_1h_bitget.csv", "5m": DATA / "xauusdt_5m_bitget.csv"}
URL = (
    "https://api.bitget.com/api/v2/mix/market/history-candles"
    "?symbol=XAUUSDT&productType=USDT-FUTURES&granularity={g}&endTime={end}&limit=200"
)


def get_page(granularity: str, end_ms: int) -> list:
    wait = 2.0
    for _ in range(8):
        req = urllib.request.Request(
            URL.format(g=granularity, end=end_ms), headers={"User-Agent": "ledger-xau/1.0"}
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode()).get("data") or []
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
        except urllib.error.URLError:
            pass
        time.sleep(wait)
        wait = min(wait * 2, 60.0)
    raise RuntimeError("Bitget kept failing; re-run to resume")


def save(path: Path, df: pd.DataFrame) -> None:
    out = df[~df.index.duplicated(keep="last")].sort_index()
    out = out.copy()
    out.insert(0, "ts", out.index)
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False)


def seed_from_now(granularity: str) -> pd.DataFrame:
    end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    data = get_page(granularity, end_ms)
    if not data:
        raise RuntimeError(f"no seed data for {granularity}")
    rows = {
        int(r[0]): [float(r[1]), float(r[2]), float(r[3]), float(r[4])] for r in data
    }
    df = pd.DataFrame.from_dict(rows, orient="index", columns=["open", "high", "low", "close"])
    df.index = pd.to_datetime(df.index, unit="ms", utc=True)
    return df.sort_index()


def extend(granularity: str, start: datetime) -> None:
    path = FILES[granularity]
    if path.exists() and path.stat().st_size > 50:
        cur = load_csv(path)
    else:
        cur = seed_from_now(granularity)
        save(path, cur)
        print(f"{granularity}: seeded {len(cur)} bars", flush=True)

    start_ms = int(start.timestamp() * 1000)
    end_ms = int(cur.index.min().value // 1_000_000) - 1
    if end_ms <= start_ms:
        print(f"{granularity}: already covers {start.date()} → {cur.index.max()}", flush=True)
        return

    print(f"{granularity}: fetch back to {start.date()} from {cur.index.min()}", flush=True)
    rows: dict[int, list[float]] = {}
    page = 0
    while end_ms > start_ms:
        data = get_page(granularity, end_ms)
        if not data:
            break
        oldest = min(int(r[0]) for r in data)
        for r in data:
            ts = int(r[0])
            if ts >= start_ms:
                rows[ts] = [float(r[1]), float(r[2]), float(r[3]), float(r[4])]
        page += 1
        if oldest >= end_ms:
            break
        end_ms = oldest - 1
        time.sleep(0.12)
        if page % 80 == 0:
            chunk = pd.DataFrame.from_dict(
                rows, orient="index", columns=["open", "high", "low", "close"]
            )
            chunk.index = pd.to_datetime(chunk.index, unit="ms", utc=True)
            cur = pd.concat([chunk, cur])
            save(path, cur)
            rows.clear()
            print(f"  {granularity} page {page} saved, now from {cur.index.min()}", flush=True)
    if rows:
        chunk = pd.DataFrame.from_dict(
            rows, orient="index", columns=["open", "high", "low", "close"]
        )
        chunk.index = pd.to_datetime(chunk.index, unit="ms", utc=True)
        cur = pd.concat([chunk, cur])
        save(path, cur)
    cur = load_csv(path)
    print(f"{granularity}: {len(cur)} bars {cur.index.min()} .. {cur.index.max()}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2024-01-01")
    args = ap.parse_args()
    start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
    for g in ("1H", "5m"):
        extend(g, start)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
