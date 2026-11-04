#!/usr/bin/env python3
"""LEDGER ICT Short — backtest / grid entrypoint."""
from __future__ import annotations

import argparse
import json
import sys

from ledger_search import run_grid, run_single


def main() -> int:
    ap = argparse.ArgumentParser(description="LEDGER ICT Short book")
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("grid", help="Search window grid + holdout top20")
    g.add_argument("--resume", action="store_true")
    g.add_argument("--tag", default="", help="suffix for workdir/excel name")

    b = sub.add_parser("backtest", help="Single param run (search + holdout)")
    b.add_argument("--swing", type=int, default=8)
    b.add_argument("--atr", type=float, default=0.6)
    b.add_argument("--fib", choices=["immediate", "wait"], default="immediate")
    b.add_argument("--wick", action="store_true")
    b.add_argument(
        "--bias-mode",
        choices=["need_color", "ignore_color"],
        default="need_color",
    )

    args = ap.parse_args()
    if args.cmd == "grid":
        path = run_grid("short", resume=args.resume, tag=args.tag)
        print(path)
        return 0
    out = run_single(
        "short",
        swing_len=args.swing,
        min_swing_atr=args.atr,
        fib_mode=args.fib,
        eq_wick=args.wick,
        bias_sweep_mode=args.bias_mode,
    )
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
