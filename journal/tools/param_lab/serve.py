#!/usr/bin/env python3
"""LEDGER param lab — local backtest explorer for Long / Short.

Usage:
  cd journal/tools/param_lab
  python serve.py

Open http://127.0.0.1:8766
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
import threading
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ledger_engine import Params, backtest  # noqa: E402
from parity_tv_last365 import bull_ifvg_ok, load_csv  # noqa: E402

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
H1 = ROOT / "data" / "btcusdt_1h_bitget.csv"
M1 = ROOT / "data" / "btcusdt_1m_bitget.csv"
M5 = ROOT / "data" / "btcusdt_5m_bitget.csv"

_lock = threading.Lock()
_cache: dict[str, Any] = {}


def bear_ifvg_ok(
    h1: pd.DataFrame,
    ltf: pd.DataFrame,
    max_age: int,
    *,
    htf_minutes: int = 60,
) -> np.ndarray:
    """Bearish IFVG: bullish FVG then close below its bottom (Pine short)."""
    low = ltf["low"].to_numpy()
    high = ltf["high"].to_numpy()
    close = ltf["close"].to_numpy()
    n = len(ltf)
    age = np.full(n, 10_000, dtype=int)
    last_bot = np.nan
    last_inv = -10_000
    for i in range(n):
        if i >= 2 and high[i - 2] < low[i]:
            last_bot = high[i - 2]
        if not np.isnan(last_bot) and close[i] < last_bot and (i == 0 or close[i - 1] >= last_bot):
            last_inv = i
        if last_inv >= 0:
            age[i] = i - last_inv
    htf_close = h1.index + pd.Timedelta(minutes=htf_minutes)
    pos = np.searchsorted(ltf.index.asi8, htf_close.asi8, side="left") - 1
    ok = np.zeros(len(h1), dtype=bool)
    valid = pos >= 0
    ok[valid] = age[pos[valid]] <= max_age
    return ok


def ensure_data(days: int = 365, warm_days: int = 60) -> dict[str, Any]:
    key = f"{days}:{warm_days}"
    with _lock:
        if key in _cache:
            return _cache[key]
    end = datetime.now(timezone.utc)
    entry_from = end - timedelta(days=days)
    warm = entry_from - timedelta(days=warm_days)
    h1 = load_csv(H1)
    h1 = h1.loc[h1.index >= pd.Timestamp(warm)].copy()
    start_i = int(np.searchsorted(h1.index.asi8, pd.Timestamp(entry_from).value, side="left"))
    m1 = load_csv(M1) if M1.exists() else None
    m5 = load_csv(M5) if M5.exists() else None
    payload = {
        "h1": h1,
        "m1": m1,
        "m5": m5,
        "start_i": start_i,
        "entry_from": entry_from.isoformat(),
        "warm": warm.isoformat(),
        "bars": len(h1),
    }
    with _lock:
        _cache[key] = payload
    return payload


def ifvg_array(side: str, ltf_tf: str, age: int, data: dict, require_ifvg: bool) -> np.ndarray | None:
    if not require_ifvg:
        return None
    h1 = data["h1"]
    ltf = data["m1"] if ltf_tf == "1" else data["m5"]
    if ltf is None:
        raise RuntimeError(f"Missing {ltf_tf}m CSV under journal/tools/data/")
    if side == "long":
        return bull_ifvg_ok(h1, ltf, age)
    return bear_ifvg_ok(h1, ltf, age)


def as_bool(v: Any, default: bool = False) -> bool:
    if v is None:
        return default
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on")
    return bool(v)


def params_from_body(body: dict, side: str) -> Params:
    is_long = side == "long"
    return Params(
        swing_len=int(body.get("swing_len", 8)),
        min_swing_atr=float(body.get("min_swing_atr", 0.6)),
        atr_len=14,
        fib_mode=body.get("fib_mode", "immediate"),  # type: ignore
        entry_mode=body.get("entry_mode", "zone_fvg_ob"),  # type: ignore
        bias_filter=body.get("bias_filter", "aligned"),  # type: ignore
        short_filter="long_only" if is_long else "match",  # type: ignore
        rr_mult=2.0,
        sl_mode="fixed_usd",
        fixed_usd_sl=float(body.get("fixed_usd_sl", 500 if is_long else 1000)),
        zone_keep=80,
        max_zones=12,
        reenter=as_bool(body.get("reenter"), True),
        cooldown=int(body.get("cooldown", 10)),
        post_stop_cooldown=int(body.get("post_stop_cooldown", 10)),
        lock_fib_on_stop=as_bool(body.get("lock_fib_on_stop"), False),
        min_hold_bars=0,
        be_trigger_r=0.0,
        doji_body_pct=10.0,
        require_body=as_bool(body.get("require_body"), True),
        commission_pct=0.04,
        initial_capital=10_000.0,
        eq_wick=as_bool(body.get("eq_wick"), True),
        use_fixed_dollar=True,
        fixed_tp_usd=float(body.get("fixed_tp_usd", 1000 if is_long else 2000)),
        fixed_risk_usd=float(body.get("fixed_risk_usd", 500)),
        allow_long=is_long,
    )


def metrics_row(m, tag: str = "") -> dict:
    return {
        "tag": tag,
        "trades": int(m.trades),
        "wins": int(m.wins),
        "wr": round(float(m.wr), 2),
        "pf": round(float(m.pf), 3),
        "pnl": round(float(m.pnl), 1),
        "pnl_pct": round(float(m.pnl_pct), 2),
        "max_dd": round(float(m.max_dd), 1),
        "max_dd_pct": round(float(m.max_dd_pct), 2),
        "avg_r": round(float(m.avg_r), 3),
        "score": round(float(m.score()), 2),
    }


def run_one(body: dict) -> dict:
    side = body.get("side", "long")
    days = int(body.get("days", 365))
    data = ensure_data(days=days)
    require_ifvg = as_bool(body.get("require_ifvg"), True)
    ltf_tf = str(body.get("ltf_tf", "1"))
    ifvg_age = int(body.get("ifvg_age", 12))
    ifvg = ifvg_array(side, ltf_tf, ifvg_age, data, require_ifvg)
    p = params_from_body(body, side)
    m = backtest(data["h1"], p, ifvg_ok=ifvg, start_i=data["start_i"])
    return {
        "ok": True,
        "side": side,
        "days": days,
        "entry_from": data["entry_from"],
        "bars": data["bars"],
        "params": {
            "swing_len": p.swing_len,
            "min_swing_atr": p.min_swing_atr,
            "fib_mode": p.fib_mode,
            "entry_mode": p.entry_mode,
            "bias_filter": p.bias_filter,
            "eq_wick": p.eq_wick,
            "cooldown": p.cooldown,
            "post_stop_cooldown": p.post_stop_cooldown,
            "require_ifvg": require_ifvg,
            "ltf_tf": ltf_tf,
            "ifvg_age": ifvg_age,
            "fixed_usd_sl": p.fixed_usd_sl,
            "fixed_tp_usd": p.fixed_tp_usd,
            "fixed_risk_usd": p.fixed_risk_usd,
        },
        "metrics": metrics_row(m),
    }


def run_grid(body: dict) -> dict:
    side = body.get("side", "long")
    days = int(body.get("days", 365))
    data = ensure_data(days=days)
    sl_default = 500 if side == "long" else 1000
    tp_default = 1000 if side == "long" else 2000

    def axis(name: str, default):
        v = body.get(name, default)
        if isinstance(v, list):
            return v if v else [default]
        return [v]

    axes = {
        "swing_len": [int(x) for x in axis("swing_len", 8)],
        "min_swing_atr": [float(x) for x in axis("min_swing_atr", 0.6)],
        "fib_mode": axis("fib_mode", "immediate"),
        "entry_mode": axis("entry_mode", "zone_fvg_ob"),
        "bias_filter": axis("bias_filter", "aligned"),
        "eq_wick": [as_bool(x, True) for x in axis("eq_wick", True)],
        "cooldown": [int(x) for x in axis("cooldown", 10)],
        "post_stop_cooldown": [int(x) for x in axis("post_stop_cooldown", 10)],
        "require_ifvg": [as_bool(x, True) for x in axis("require_ifvg", True)],
        "require_body": [as_bool(x, True) for x in axis("require_body", True)],
        "reenter": [as_bool(x, True) for x in axis("reenter", True)],
        "lock_fib_on_stop": [as_bool(x, False) for x in axis("lock_fib_on_stop", False)],
        "ltf_tf": [str(x) for x in axis("ltf_tf", "1")],
        "ifvg_age": [int(x) for x in axis("ifvg_age", 12)],
        "fixed_usd_sl": [float(x) for x in axis("fixed_usd_sl", sl_default)],
        "fixed_tp_usd": [float(x) for x in axis("fixed_tp_usd", tp_default)],
        "fixed_risk_usd": [float(x) for x in axis("fixed_risk_usd", 500)],
    }
    keys = list(axes.keys())
    combos = list(itertools.product(*axes.values()))
    if len(combos) > 216:
        return {"ok": False, "error": f"Too many combos ({len(combos)}). Cap is 216."}

    ifvg_cache: dict[tuple, Any] = {}
    rows = []
    for vals in combos:
        cfg = dict(zip(keys, vals))
        ltf = str(cfg["ltf_tf"])
        age = int(cfg["ifvg_age"])
        req_ifvg = bool(cfg["require_ifvg"])
        ikey = (ltf, age, req_ifvg)
        if ikey not in ifvg_cache:
            ifvg_cache[ikey] = ifvg_array(side, ltf, age, data, req_ifvg)
        ifvg = ifvg_cache[ikey]
        p = params_from_body({**body, **cfg}, side)
        sl = int(cfg["fixed_usd_sl"])
        tp = int(cfg["fixed_tp_usd"])
        risk = int(cfg["fixed_risk_usd"])
        tag = (
            f"sw{cfg['swing_len']} a{cfg['min_swing_atr']} {cfg['fib_mode']} "
            f"{cfg['entry_mode']} {cfg['bias_filter']} "
            f"{'wick' if cfg['eq_wick'] else 'close'} "
            f"c{cfg['cooldown']}/{cfg['post_stop_cooldown']} "
            f"{'ifvg' if req_ifvg else 'ifvgoff'}{ltf}m@{age} "
            f"SL{sl}/TP{tp}/R{risk}"
        )
        row = metrics_row(
            backtest(data["h1"], p, ifvg_ok=ifvg, start_i=data["start_i"]), tag
        )
        row.update(cfg)
        rows.append(row)

    rows.sort(key=lambda r: (r["score"], r["pf"], r["pnl_pct"]), reverse=True)
    if rows:
        best_s = rows[0]["score"]
        worst_s = rows[-1]["score"]
        for i, r in enumerate(rows):
            r["rank"] = i + 1
            r["place"] = (
                "best" if r["score"] == best_s else "worst" if r["score"] == worst_s and len(rows) > 1 else ""
            )
    return {
        "ok": True,
        "side": side,
        "days": days,
        "combos": len(rows),
        "entry_from": data["entry_from"],
        "rows": rows,
    }


class Handler(BaseHTTPRequestHandler):
    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            body = (STATIC / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self._cors()
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/health":
            return self._json(200, {"ok": True, "h1": H1.exists(), "m1": M1.exists(), "m5": M5.exists()})
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n) if n else b"{}"
        try:
            body = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            return self._json(400, {"ok": False, "error": "bad json"})
        try:
            if path == "/api/run":
                return self._json(200, run_one(body))
            if path == "/api/grid":
                return self._json(200, run_grid(body))
        except Exception as exc:
            return self._json(500, {"ok": False, "error": str(exc)})
        self.send_error(404)

    def _json(self, code: int, obj: dict) -> None:
        raw = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()
    print("Loading Bitget caches…", flush=True)
    d = ensure_data(365)
    print(f"H1 bars={d['bars']} entry_from={d['entry_from'][:10]}", flush=True)
    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Param lab -> {url}", flush=True)
    if not args.no_open:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
