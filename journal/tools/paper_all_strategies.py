#!/usr/bin/env python3
"""Paper every named strategy across calendar years + combined long/short books.

Shared-equity combined books: merge trade logs by time, risk fixed $ per trade
from shared capital, optional kill-switch when equity DD from peak hits max_dd_pct.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from ledger_engine import Params, backtest
from ledger_search import FIXED, bear_ifvg_ok, make_params, resolve_h1, resolve_ltf
from parity_tv_last365 import bull_ifvg_ok, load_csv

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"
DATA = ROOT / "data"
CAPITAL = 10_000.0
RISK = 500.0  # cash risked per trade (matches fixed_risk_usd)


@dataclass(frozen=True)
class Strat:
    name: str
    side: str  # long | short
    swing: int
    atr: float
    fib: str
    wick: bool
    bias: str
    source: str


# Named strategies we care about (not raw 224 cartesian — that already ran)
STRATS = [
    Strat("Old LONG champ", "long", 12, 0.6, "immediate", False, "need_color", "prior holdout pick"),
    Strat("Old SHORT least-bad", "short", 14, 0.6, "immediate", True, "need_color", "prior holdout pick"),
    Strat("2024-grid LONG holdout#1", "long", 8, 0.6, "immediate", False, "need_color", "tuned on 2024"),
    Strat("2024-grid SHORT holdout#1", "short", 10, 0.6, "immediate", True, "need_color", "tuned on 2024"),
    Strat("2024-grid SHORT search#1", "short", 12, 1.2, "immediate", True, "need_color", "2024 search peak"),
    Strat("Alt LONG swing10", "long", 10, 0.6, "immediate", False, "need_color", "mid swing"),
    Strat("Alt LONG swing14", "long", 14, 0.6, "immediate", False, "need_color", "mid swing"),
    Strat("Alt SHORT swing8 wick", "short", 8, 0.6, "immediate", True, "need_color", "more frequent short"),
]

# Combined books: (name, long_strat_name, short_strat_name, max_dd_kill_pct or None)
COMBOS = [
    ("Combo: 2024 LONG#1 + SHORT#1", "2024-grid LONG holdout#1", "2024-grid SHORT holdout#1", None),
    ("Combo: 2024 L+S, kill@25%DD", "2024-grid LONG holdout#1", "2024-grid SHORT holdout#1", 25.0),
    ("Combo: 2024 L+S, kill@35%DD", "2024-grid LONG holdout#1", "2024-grid SHORT holdout#1", 35.0),
    ("Combo: Old LONG + 2024 SHORT", "Old LONG champ", "2024-grid SHORT holdout#1", None),
    ("Combo: Old LONG + Old SHORT", "Old LONG champ", "Old SHORT least-bad", None),
    ("Combo: Old L+S, kill@25%DD", "Old LONG champ", "Old SHORT least-bad", 25.0),
]


def load_full():
    h1 = load_csv(resolve_h1())
    ltf_path, ltf_name = resolve_ltf()
    ltf = load_csv(ltf_path)
    start = max(h1.index.min(), ltf.index.min())
    h1 = h1.loc[h1.index >= start].copy()
    ltf = ltf.loc[ltf.index >= start].copy()
    # warm 60d before first trade year
    warm = pd.Timestamp("2024-01-01", tz="UTC") - pd.Timedelta(days=60)
    h1 = h1.loc[h1.index >= warm].copy()
    ltf = ltf.loc[ltf.index >= warm].copy()
    print(f"data {h1.index.min().date()} .. {h1.index.max().date()} ltf={ltf_name}", flush=True)
    print("building IFVG long/short ...", flush=True)
    return h1, bull_ifvg_ok(h1, ltf, 12), bear_ifvg_ok(h1, ltf, 12)


def trades_for(h1, ifvg_bull, ifvg_bear, s: Strat) -> pd.DataFrame:
    p = make_params(s.side, s.swing, s.atr, s.fib, s.wick, s.bias)
    ifvg = ifvg_bull if s.side == "long" else ifvg_bear
    start_i = int(np.searchsorted(h1.index.asi8, pd.Timestamp("2024-01-01", tz="UTC").value, side="left"))
    m = backtest(h1, p, ifvg_ok=ifvg, start_i=start_i, collect_trades=True)
    rows = []
    for t in m.trade_log:  # type: ignore[attr-defined]
        rows.append(
            {
                "strategy": s.name,
                "side": t["side"],
                "entry_time": pd.Timestamp(t["entry_time"]),
                "exit_time": pd.Timestamp(t["exit_time"]),
                "pnl": float(t["pnl"]),
                "r": float(t["pnl"]) / RISK,
                "is_stop": bool(t["is_stop"]),
            }
        )
    return pd.DataFrame(rows)


def summarize(trades: pd.DataFrame, capital: float = CAPITAL) -> dict:
    if trades is None or len(trades) == 0:
        return dict(trades=0, wins=0, wr=0.0, pf=0.0, pnl=0.0, pnl_pct=0.0, max_dd_pct=0.0, avg_r=0.0, total_r=0.0)
    eq = capital
    peak = capital
    max_dd_pct = 0.0
    pnls = trades["pnl"].to_list()
    for pnl in pnls:
        eq += pnl
        peak = max(peak, eq)
        max_dd_pct = max(max_dd_pct, (peak - eq) / peak * 100.0 if peak > 0 else 0.0)
    wins = sum(1 for x in pnls if x > 0)
    gw = sum(x for x in pnls if x > 0)
    gl = abs(sum(x for x in pnls if x <= 0))
    return dict(
        trades=len(pnls),
        wins=wins,
        wr=round(100.0 * wins / len(pnls), 1),
        pf=round(gw / gl, 3) if gl > 0 else (99.0 if wins else 0.0),
        pnl=round(sum(pnls), 1),
        pnl_pct=round(100.0 * sum(pnls) / capital, 2),
        max_dd_pct=round(max_dd_pct, 2),
        avg_r=round(float(np.mean(trades["r"])), 3),
        total_r=round(float(trades["r"].sum()), 2),
    )


def by_year(trades: pd.DataFrame) -> pd.DataFrame:
    if len(trades) == 0:
        return pd.DataFrame()
    t = trades.copy()
    t["year"] = t["exit_time"].dt.year
    rows = []
    for y, g in t.groupby("year"):
        s = summarize(g)
        s["year"] = int(y)
        rows.append(s)
    # full
    s = summarize(trades)
    s["year"] = "ALL"
    rows.append(s)
    return pd.DataFrame(rows)


def combine(long_t: pd.DataFrame, short_t: pd.DataFrame, max_dd_kill: float | None) -> pd.DataFrame:
    """Replay exits in time order; size already baked into pnl at RISK from initial capital.
    Approximate shared book: scale each trade's pnl by (current_equity / CAPITAL) so risk
    stays ~5% of live equity; stop new entries after kill DD.
    """
    parts = []
    if len(long_t):
        parts.append(long_t.assign(book="long"))
    if len(short_t):
        parts.append(short_t.assign(book="short"))
    if not parts:
        return pd.DataFrame(columns=long_t.columns)
    all_t = pd.concat(parts, ignore_index=True).sort_values("exit_time").reset_index(drop=True)

    eq = CAPITAL
    peak = CAPITAL
    killed = False
    out = []
    for _, row in all_t.iterrows():
        if killed:
            continue
        # scale from $10k-risked pnl to current equity 5% risk
        scale = eq / CAPITAL
        pnl = float(row["pnl"]) * scale
        risk_cash = RISK * scale
        eq += pnl
        peak = max(peak, eq)
        dd = (peak - eq) / peak * 100.0 if peak > 0 else 0.0
        out.append({**row.to_dict(), "pnl": pnl, "r": pnl / max(risk_cash, 1e-9)})
        if max_dd_kill is not None and dd >= max_dd_kill:
            killed = True
    return pd.DataFrame(out)


def main() -> int:
    h1, ifvg_bull, ifvg_bear = load_full()
    by_name: dict[str, pd.DataFrame] = {}
    single_rows = []
    year_rows = []

    for s in STRATS:
        print(f"run {s.name} ...", flush=True)
        t = trades_for(h1, ifvg_bull, ifvg_bear, s)
        by_name[s.name] = t
        summary = summarize(t)
        single_rows.append({"strategy": s.name, "side": s.side, "source": s.source, **summary})
        ydf = by_year(t)
        if len(ydf):
            ydf.insert(0, "strategy", s.name)
            year_rows.append(ydf)

    combo_rows = []
    combo_year_rows = []
    for cname, ln, sn, kill in COMBOS:
        print(f"combine {cname} ...", flush=True)
        ct = combine(by_name[ln], by_name[sn], kill)
        summary = summarize(ct)
        combo_rows.append(
            {
                "strategy": cname,
                "long": ln,
                "short": sn,
                "max_dd_kill": kill if kill is not None else "off",
                **summary,
            }
        )
        ydf = by_year(ct)
        if len(ydf):
            ydf.insert(0, "strategy", cname)
            combo_year_rows.append(ydf)

    singles = pd.DataFrame(single_rows).sort_values(["pnl_pct", "pf"], ascending=False)
    combos = pd.DataFrame(combo_rows).sort_values(["pnl_pct", "pf"], ascending=False)
    years = pd.concat(year_rows + combo_year_rows, ignore_index=True) if year_rows else pd.DataFrame()

    # long-term worth score: total_r - 0.5*max_dd_r_proxy; use pnl_pct - 0.5*max_dd_pct
    for df in (singles, combos):
        df["worth"] = df["pnl_pct"] - 0.5 * df["max_dd_pct"]
        df.sort_values("worth", ascending=False, inplace=True)
        df.reset_index(drop=True, inplace=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = OUT / f"paper_all_strategies_{stamp}.xlsx"
    notes = pd.DataFrame(
        [
            {"item": "period", "value": "entries from 2024-01-01 through data end"},
            {"item": "risk", "value": f"${RISK} cash risk / trade (~5% of ${CAPITAL}); combined scales with live equity"},
            {"item": "kill", "value": "combined books with kill@X% stop taking new trades after peak-to-trough DD hits X"},
            {"item": "worth", "value": "pnl_pct - 0.5*max_dd_pct  (balance profit vs pain)"},
            {"item": "note", "value": "Not every grid combo — named champs + alts. Full grids already in *_search_y2024_* and prior Excels"},
        ]
    )
    with pd.ExcelWriter(path, engine="xlsxwriter") as xw:
        singles.to_excel(xw, sheet_name="Singles_Ranked", index=False)
        combos.to_excel(xw, sheet_name="Combos_Ranked", index=False)
        years.to_excel(xw, sheet_name="By_Year", index=False)
        notes.to_excel(xw, sheet_name="Notes", index=False)

    pd.set_option("display.width", 220)
    print("\n=== SINGLES (worth = pnl% - 0.5*DD%) ===")
    print(singles[["strategy", "side", "trades", "wr", "pf", "pnl_pct", "max_dd_pct", "total_r", "worth"]].to_string(index=False))
    print("\n=== COMBOS ===")
    print(combos[["strategy", "trades", "wr", "pf", "pnl_pct", "max_dd_pct", "total_r", "worth"]].to_string(index=False))
    print("\n=== BY YEAR (top lines) ===")
    print(years.to_string(index=False))
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
