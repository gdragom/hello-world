#!/usr/bin/env python3
"""
Grid-search + walk-forward for LEDGER ICT 1H params.

Examples:
  pip install -r requirements-opt.txt
  python optimize_ledger.py --download --days 730
  python optimize_ledger.py --csv data/btcusdt_1h.csv --walkforward
  python optimize_ledger.py --csv data/btcusdt_1h.csv --quick

Top rows are ranked by score (PF-heavy, min trades, DD cap).
Always re-check winners on TradingView Strategy Tester (engine ≈ TV, not identical).
"""

from __future__ import annotations

import argparse
import itertools
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from ledger_engine import Params, backtest, params_to_row

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_CSV = ROOT / "data" / "btcusdt_1h.csv"
OUT_DIR = ROOT / "out"


def download_ohlcv(symbol: str, timeframe: str, days: int, out: Path) -> pd.DataFrame:
    import ccxt

    exchange = ccxt.binanceusdm({"enableRateLimit": True})
    since = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)
    all_rows = []
    while True:
        batch = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=1000)
        if not batch:
            break
        all_rows.extend(batch)
        since = batch[-1][0] + 1
        if len(batch) < 1000:
            break
    df = pd.DataFrame(all_rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.drop_duplicates("ts").set_index("ts").sort_index()
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out)
    print(f"Wrote {len(df)} bars -> {out}")
    return df


def load_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    # accept ts / timestamp / datetime / date
    for col in ("ts", "timestamp", "datetime", "date", "time"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True)
            df = df.set_index(col)
            break
    else:
        df.iloc[:, 0] = pd.to_datetime(df.iloc[:, 0], utc=True)
        df = df.set_index(df.columns[0])
    cols = {c.lower(): c for c in df.columns}
    rename = {}
    for need in ("open", "high", "low", "close"):
        if need not in df.columns and need in cols:
            rename[cols[need]] = need
    df = df.rename(columns=rename)
    return df[["open", "high", "low", "close"]].astype(float).sort_index()


def grid(quick: bool) -> list[Params]:
    if quick:
        swings = [5, 7]
        atrs = [0.5, 0.8]
        entries = ["deep", "zone_fvg_ob"]
        fibs = ["immediate", "wait"]
        biases = ["block_opp", "aligned"]
        shorts = ["no_bull", "aligned"]
        rrs = [2.0, 2.5]
        sls = ["fib"]
        posts = [8, 12]
        bes = [1.0]
        reenters = [False]
    else:
        swings = [5, 7, 10]
        atrs = [0.5, 0.8, 1.0]
        entries = ["deep", "zone_fvg_ob"]
        fibs = ["immediate", "wait"]
        biases = ["block_opp", "aligned"]
        shorts = ["no_bull", "aligned", "long_only"]
        rrs = [2.0, 2.5]
        sls = ["fib", "fixed_usd"]
        posts = [6, 10]
        bes = [0.0, 1.0]
        reenters = [False]

    out = []
    for sl, ma, em, fm, bf, sf, rr, sm, post, be, re in itertools.product(
        swings, atrs, entries, fibs, biases, shorts, rrs, sls, posts, bes, reenters
    ):
        out.append(
            Params(
                swing_len=sl,
                min_swing_atr=ma,
                fib_mode=fm,  # type: ignore
                entry_mode=em,  # type: ignore
                bias_filter=bf,  # type: ignore
                short_filter=sf,  # type: ignore
                rr_mult=rr,
                sl_mode=sm,  # type: ignore
                fixed_usd_sl=500.0,
                reenter=re,
                cooldown=8 if not re else 4,
                post_stop_cooldown=post,
                lock_fib_on_stop=True,
                min_hold_bars=4,
                be_trigger_r=be,
            )
        )
    return out


def run_grid(df: pd.DataFrame, combos: list[Params], tag: str) -> pd.DataFrame:
    rows = []
    total = len(combos)
    for i, p in enumerate(combos, 1):
        m = backtest(df, p)
        rows.append(params_to_row(p, m, tag=tag))
        if i % 25 == 0 or i == total:
            print(f"  [{tag}] {i}/{total} ... best score so far {max(r['rank_score'] for r in rows):.1f}")
    return pd.DataFrame(rows).sort_values("rank_score", ascending=False)


def walk_forward(df: pd.DataFrame, combos: list[Params], windows: int = 3, oos: float = 0.3) -> pd.DataFrame:
    """For each window: pick best IS combo, measure OOS."""
    n = len(df)
    win_size = n // windows
    oos_rows = []
    for w in range(windows):
        start = w * win_size
        end = n if w == windows - 1 else (w + 1) * win_size
        chunk = df.iloc[start:end]
        split = int(len(chunk) * (1 - oos))
        if split < 200 or len(chunk) - split < 100:
            continue
        is_df = chunk.iloc[:split]
        oos_df = chunk.iloc[split:]
        print(f"WF window {w + 1}/{windows}: IS {is_df.index[0].date()}->{is_df.index[-1].date()} "
              f"OOS {oos_df.index[0].date()}->{oos_df.index[-1].date()}")
        is_rank = run_grid(is_df, combos, tag=f"IS{w+1}")
        best = is_rank.iloc[0]
        p = Params(
            swing_len=int(best["swing_len"]),
            min_swing_atr=float(best["min_swing_atr"]),
            fib_mode=best["fib_mode"],
            entry_mode=best["entry_mode"],
            bias_filter=best["bias_filter"],
            short_filter=best["short_filter"],
            rr_mult=float(best["rr_mult"]),
            sl_mode=best["sl_mode"],
            reenter=bool(best["reenter"]),
            cooldown=int(best["cooldown"]),
            post_stop_cooldown=int(best["post_stop_cooldown"]),
            be_trigger_r=float(best["be_trigger_r"]),
            min_hold_bars=int(best["min_hold_bars"]),
        )
        m = backtest(oos_df, p)
        row = params_to_row(p, m, tag=f"OOS{w+1}")
        row["is_pf"] = best["pf"]
        row["is_wr"] = best["wr"]
        oos_rows.append(row)
        print(f"  -> OOS trades={m.trades} WR={m.wr:.1f}% PF={m.pf:.3f} PnL%={m.pnl_pct:.2f}")
    return pd.DataFrame(oos_rows)


def main() -> int:
    ap = argparse.ArgumentParser(description="LEDGER ICT 1H parameter optimizer")
    ap.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="OHLCV CSV path")
    ap.add_argument("--download", action="store_true", help="Download Binance USDM BTC 1H via ccxt")
    ap.add_argument("--symbol", default="BTC/USDT:USDT")
    ap.add_argument("--days", type=int, default=800)
    ap.add_argument("--quick", action="store_true", help="Smaller grid")
    ap.add_argument("--walkforward", action="store_true", help="IS optimize + OOS validate")
    ap.add_argument("--windows", type=int, default=4, help="Walk-forward windows (default 4 on recent slice)")
    ap.add_argument("--recent-years", type=float, default=2.0,
                    help="Use only last N years of CSV before tune/WF (0 = full). Default 2.")
    ap.add_argument("--tune-days", type=int, default=365, help="Tune grid on last N days within recent slice")
    ap.add_argument("--confirm-days", type=int, default=365, help="Confirm prior N days before tune")
    ap.add_argument("--top", type=int, default=15)
    args = ap.parse_args()

    if args.download or not args.csv.exists():
        if not args.download and not args.csv.exists():
            print(f"No CSV at {args.csv}; downloading...")
        df = download_ohlcv(args.symbol, "1h", args.days, args.csv)
    else:
        df = load_csv(args.csv)
        print(f"Loaded {len(df)} bars from {args.csv}")

    if args.recent_years and args.recent_years > 0:
        bars = int(args.recent_years * 365 * 24)
        if len(df) > bars:
            df = df.iloc[-bars:]
            print(f"Recent {args.recent_years}y slice: {df.index[0].date()} -> {df.index[-1].date()} ({len(df)} bars)")

    combos = grid(quick=args.quick)
    print(f"Grid size: {len(combos)}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    if args.walkforward:
        wf = walk_forward(df, combos, windows=args.windows)
        out = OUT_DIR / f"walkforward_{stamp}.csv"
        wf.to_csv(out, index=False)
        print(f"\nWalk-forward saved -> {out}")
        if len(wf):
            print(wf[["tag", "swing_len", "min_swing_atr", "entry_mode", "fib_mode",
                      "bias_filter", "short_filter", "rr_mult", "post_stop_cooldown", "be_trigger_r",
                      "trades", "wr", "pf", "pnl_pct", "max_dd_pct"]].to_string(index=False))
        return 0

    # Single-slice grid on last tune-days
    if args.tune_days and len(df) > args.tune_days * 24:
        df_tune = df.iloc[-args.tune_days * 24 :]
    else:
        df_tune = df
    print(f"Tune slice: {df_tune.index[0]} -> {df_tune.index[-1]} ({len(df_tune)} bars)")

    ranked = run_grid(df_tune, combos, tag="tune")
    out = OUT_DIR / f"grid_{stamp}.csv"
    ranked.to_csv(out, index=False)
    print(f"\nFull grid -> {out}")
    cols = ["swing_len", "min_swing_atr", "entry_mode", "fib_mode", "bias_filter", "short_filter",
            "rr_mult", "sl_mode", "post_stop_cooldown", "be_trigger_r", "reenter",
            "trades", "wr", "pf", "pnl_pct", "max_dd_pct", "rank_score"]
    print("\nTOP RESULTS")
    print(ranked[cols].head(args.top).to_string(index=False))

    # Confirm: prior confirm-days if available
    need = (args.tune_days + args.confirm_days) * 24
    if len(df) > need:
        confirm = df.iloc[-(args.tune_days + args.confirm_days) * 24 : -args.tune_days * 24]
        print(f"\nConfirm slice: {confirm.index[0].date()} -> {confirm.index[-1].date()}")
        top_params = []
        for _, row in ranked.head(5).iterrows():
            top_params.append(
                Params(
                    swing_len=int(row["swing_len"]),
                    min_swing_atr=float(row["min_swing_atr"]),
                    fib_mode=row["fib_mode"],
                    entry_mode=row["entry_mode"],
                    bias_filter=row["bias_filter"],
                    short_filter=row["short_filter"],
                    rr_mult=float(row["rr_mult"]),
                    sl_mode=row["sl_mode"],
                    reenter=bool(row["reenter"]),
                    cooldown=int(row["cooldown"]),
                    post_stop_cooldown=int(row["post_stop_cooldown"]),
                    be_trigger_r=float(row["be_trigger_r"]),
                    min_hold_bars=int(row["min_hold_bars"]),
                )
            )
        conf_df = run_grid(confirm, top_params, tag="confirm")
        cout = OUT_DIR / f"confirm_{stamp}.csv"
        conf_df.to_csv(cout, index=False)
        print(conf_df[cols].to_string(index=False))
        print(f"Confirm -> {cout}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
