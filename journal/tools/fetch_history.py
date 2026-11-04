#!/usr/bin/env python3
"""Download / extend Bitget BTCUSDT USDT-FUTURES candles (resumable, rate-limit safe).

Walks history-candles until the API returns nothing (or --start). Also fills
the newest gap up to now. 1H / 5m / 1m.

  python fetch_history.py
  python fetch_history.py --tf 1H 5m
"""
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
FILES = {
    "1H": DATA / "btcusdt_1h_bitget.csv",
    "5m": DATA / "btcusdt_5m_bitget.csv",
    "1m": DATA / "btcusdt_1m_bitget.csv",
}
URL = (
    "https://api.bitget.com/api/v2/mix/market/history-candles"
    "?symbol=BTCUSDT&productType=USDT-FUTURES&granularity={g}&endTime={end}&limit=200"
)
COLS = ["open", "high", "low", "close"]


def get_page(granularity: str, end_ms: int) -> list:
    wait = 2.0
    for _ in range(8):
        req = urllib.request.Request(
            URL.format(g=granularity, end=end_ms),
            headers={"User-Agent": "ledger-fetch/1.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode())
            return payload.get("data") or []
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
        except urllib.error.URLError:
            pass
        time.sleep(wait)
        wait = min(wait * 2, 60.0)
    raise RuntimeError("Bitget kept failing; re-run to resume")


def rows_to_df(rows: dict[int, list[float]]) -> pd.DataFrame:
    chunk = pd.DataFrame.from_dict(rows, orient="index", columns=COLS)
    chunk.index = pd.to_datetime(chunk.index, unit="ms", utc=True)
    return chunk.sort_index()


def save(path: Path, df: pd.DataFrame) -> None:
    out = df[~df.index.duplicated(keep="last")].sort_index()[COLS].copy()
    out.insert(0, "ts", out.index)
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False)


def load_or_empty(path: Path) -> pd.DataFrame:
    if path.exists() and path.stat().st_size > 80:
        return load_csv(path)
    return pd.DataFrame(columns=COLS)


def merge(cur: pd.DataFrame, extra: pd.DataFrame) -> pd.DataFrame:
    if extra.empty:
        return cur
    if cur.empty:
        return extra
    return pd.concat([cur, extra])[~pd.concat([cur, extra]).index.duplicated(keep="last")].sort_index()


def walk(granularity: str, end_ms: int, stop_ms: int, existing_max_ms: int | None) -> dict[int, list[float]]:
    """Pages backward from end_ms down to stop_ms. Stops early if we overlap existing_max."""
    rows: dict[int, list[float]] = {}
    page = 0
    while end_ms > stop_ms:
        data = get_page(granularity, end_ms)
        if not data:
            break
        oldest = min(int(r[0]) for r in data)
        newest = max(int(r[0]) for r in data)
        for r in data:
            ts = int(r[0])
            if ts >= stop_ms:
                rows[ts] = [float(r[1]), float(r[2]), float(r[3]), float(r[4])]
        page += 1
        if existing_max_ms is not None and oldest <= existing_max_ms:
            break
        if oldest >= end_ms or len(data) < 200:
            break
        end_ms = oldest - 1
        time.sleep(0.12)
        if page % 80 == 0:
            print(
                f"  {granularity} page {page} +{len(rows)} bars  {pd.to_datetime(oldest, unit='ms', utc=True)}",
                flush=True,
            )
    return rows


def fill_forward(granularity: str, path: Path) -> pd.DataFrame:
    cur = load_or_empty(path)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    if cur.empty:
        print(f"{granularity}: empty cache - fetching from now backward...", flush=True)
        extra = walk(granularity, now_ms, 0, None)
        cur = rows_to_df(extra) if extra else cur
        if not cur.empty:
            save(path, cur)
        return cur
    newest = int(cur.index.max().value // 1_000_000)
    if now_ms - newest < 60_000:
        print(f"{granularity}: already current ({cur.index.max()})", flush=True)
        return cur
    print(f"{granularity}: fill newest {cur.index.max()} -> now", flush=True)
    extra = walk(granularity, now_ms, newest, newest)
    if extra:
        cur = merge(cur, rows_to_df(extra))
        save(path, cur)
    return cur


def fill_back(granularity: str, path: Path, start: datetime | None) -> pd.DataFrame:
    cur = load_or_empty(path)
    if cur.empty:
        return cur
    stop_ms = int(start.timestamp() * 1000) if start else 0
    oldest = int(cur.index.min().value // 1_000_000)
    if oldest <= stop_ms + 60_000:
        print(f"{granularity}: already as far back as {cur.index.min()}", flush=True)
        return cur
    print(f"{granularity}: fetch older than {cur.index.min()}", flush=True)
    rows: dict[int, list[float]] = {}
    end_ms = oldest - 1
    page = 0
    while end_ms > stop_ms:
        data = get_page(granularity, end_ms)
        if not data:
            print(f"  {granularity}: Bitget returned no older candles", flush=True)
            break
        got_oldest = min(int(r[0]) for r in data)
        for r in data:
            ts = int(r[0])
            if ts >= stop_ms:
                rows[ts] = [float(r[1]), float(r[2]), float(r[3]), float(r[4])]
        page += 1
        if got_oldest >= end_ms or len(data) < 200:
            break
        end_ms = got_oldest - 1
        time.sleep(0.12)
        if page % 80 == 0:
            chunk = rows_to_df(rows)
            cur = merge(cur, chunk)
            save(path, cur)
            rows.clear()
            print(f"  {granularity} page {page} saved, now from {cur.index.min()}", flush=True)
    if rows:
        cur = merge(cur, rows_to_df(rows))
        save(path, cur)
    return cur


def sync_tf(granularity: str, start: datetime | None) -> None:
    path = FILES[granularity]
    cur = fill_forward(granularity, path)
    cur = fill_back(granularity, path, start)
    print(f"{granularity}: {len(cur)} bars {cur.index.min()} .. {cur.index.max()}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="", help="UTC date floor (YYYY-MM-DD). Empty = until Bitget has nothing older.")
    ap.add_argument("--tf", nargs="+", default=["1H", "5m", "1m"], choices=["1H", "5m", "1m"])
    args = ap.parse_args()
    start = None
    if args.start.strip():
        start = datetime.fromisoformat(args.start.strip()).replace(tzinfo=timezone.utc)
    DATA.mkdir(parents=True, exist_ok=True)
    for g in args.tf:
        sync_tf(g, start)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
