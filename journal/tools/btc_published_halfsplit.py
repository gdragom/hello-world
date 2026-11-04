"""Published-rule BTCUSDT daily half-split. Parameters fixed before the run.

No commissions, no funding, no leverage, no buy-and-hold benchmark.
Cash yield is 0 (Faber/TSMOM papers credit T-bills; that yield is omitted).
Short side of long/short systems is flat, not short. Stated in each rule.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

DATA = Path(__file__).resolve().parent / "data" / "btcusdt_1d_bitget.json"
OUT = Path(__file__).resolve().parent / "out" / "btc_published_halfsplit.json"

# Locked before looking at results. Do not add or retune after the run.
RULES = (
    "sma150",
    "sma200",
    "sma50",
    "faber10",
    "tsmom12",
    "donchian20",
    "turtle_s2",
    "connors_rsi2",
    "ibs_long",
)


def load() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    raw = json.loads(DATA.read_text(encoding="utf-8"))
    raw.sort(key=lambda r: r["ts"])
    ts = np.array([int(r["ts"]) for r in raw], dtype=np.int64)
    o = np.array([float(r["o"]) for r in raw], dtype=float)
    h = np.array([float(r["h"]) for r in raw], dtype=float)
    l = np.array([float(r["l"]) for r in raw], dtype=float)
    c = np.array([float(r["c"]) for r in raw], dtype=float)
    if len(ts) != len(set(ts.tolist())):
        raise SystemExit("duplicate timestamps")
    if np.any(np.diff(ts) <= 0):
        raise SystemExit("timestamps not strictly increasing")
    return ts, o, h, l, c


def dates_of(ts: np.ndarray) -> list[datetime]:
    return [datetime.fromtimestamp(int(t) / 1000, tz=timezone.utc) for t in ts]


def sma(x: np.ndarray, w: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    if len(x) < w:
        return out
    cs = np.cumsum(x)
    out[w - 1] = cs[w - 1] / w
    if len(x) > w:
        out[w:] = (cs[w:] - cs[:-w]) / w
    return out


def wilder_rsi(close: np.ndarray, period: int) -> np.ndarray:
    n = len(close)
    rsi = np.full(n, np.nan)
    delta = np.diff(close, prepend=close[0])
    delta[0] = 0.0
    gain = np.maximum(delta, 0.0)
    loss = np.maximum(-delta, 0.0)
    if n <= period:
        return rsi
    avg_g = float(np.mean(gain[1 : period + 1]))
    avg_l = float(np.mean(loss[1 : period + 1]))
    rsi[period] = 100.0 if avg_l == 0 else 100.0 - 100.0 / (1.0 + avg_g / avg_l)
    for i in range(period + 1, n):
        avg_g = (avg_g * (period - 1) + gain[i]) / period
        avg_l = (avg_l * (period - 1) + loss[i]) / period
        rsi[i] = 100.0 if avg_l == 0 else 100.0 - 100.0 / (1.0 + avg_g / avg_l)
    return rsi


def wilder_atr(h: np.ndarray, l: np.ndarray, c: np.ndarray, period: int = 20) -> np.ndarray:
    n = len(c)
    tr = np.empty(n)
    tr[0] = h[0] - l[0]
    tr[1:] = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    atr = np.full(n, np.nan)
    if n < period:
        return atr
    atr[period - 1] = float(np.mean(tr[:period]))
    for i in range(period, n):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return atr


def close_to_close(pos: np.ndarray, c: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """pos[i] is the position held across the close[i-1] -> close[i] move. 0 or 1."""
    n = len(c)
    ret = np.zeros(n)
    ret[1:] = pos[1:] * (c[1:] / c[:-1] - 1.0)
    exposed = pos > 0
    return ret, exposed


def ma_long_flat(c: np.ndarray, window: int) -> tuple[np.ndarray, np.ndarray]:
    m = sma(c, window)
    pos = np.zeros(len(c))
    valid = ~np.isnan(m)
    pos[1:] = ((c[:-1] > m[:-1]) & valid[:-1]).astype(float)
    return close_to_close(pos, c)


def faber_10m(c: np.ndarray, dts: list[datetime]) -> tuple[np.ndarray, np.ndarray]:
    month_last: dict[tuple[int, int], int] = {}
    for i, d in enumerate(dts):
        month_last[(d.year, d.month)] = i
    keys = list(month_last.keys())
    pos = np.zeros(len(c))
    for j in range(9, len(keys) - 1):
        ends = [month_last[keys[k]] for k in range(j - 9, j + 1)]
        sig = c[ends[-1]] > float(np.mean(c[ends]))
        y, m = keys[j + 1]
        for i, d in enumerate(dts):
            if d.year == y and d.month == m:
                pos[i] = 1.0 if sig else 0.0
    return close_to_close(pos, c)


def tsmom_12_1(c: np.ndarray, dts: list[datetime]) -> tuple[np.ndarray, np.ndarray]:
    """Month-end close vs close 12 month-ends earlier. Long next month if > 0."""
    month_last: dict[tuple[int, int], int] = {}
    for i, d in enumerate(dts):
        month_last[(d.year, d.month)] = i
    keys = list(month_last.keys())
    pos = np.zeros(len(c))
    for j in range(12, len(keys) - 1):
        now_i = month_last[keys[j]]
        prev_i = month_last[keys[j - 12]]
        sig = c[now_i] / c[prev_i] - 1.0 > 0.0
        y, m = keys[j + 1]
        for i, d in enumerate(dts):
            if d.year == y and d.month == m:
                pos[i] = 1.0 if sig else 0.0
    return close_to_close(pos, c)


def breakout_long_flat(
    o: np.ndarray,
    h: np.ndarray,
    l: np.ndarray,
    c: np.ndarray,
    entry_n: int,
    exit_n: int,
    use_stop: bool,
) -> tuple[np.ndarray, np.ndarray]:
    """Intraday channel. 100% or flat. No pyramid, no short, no same-bar re-entry.

    If channel and 2N stop are both touched, fill at the worse (lower) price.
    """
    n = len(c)
    atr = wilder_atr(h, l, c, 20)
    equity = np.ones(n)
    cash = 1.0
    units = 0.0
    in_pos = False
    stop = -np.inf
    active = np.zeros(n, dtype=bool)
    for i in range(1, n):
        round_trip = False
        if in_pos:
            prior_low = float(np.min(l[i - exit_n : i])) if i >= exit_n else np.nan
            channel_hit = i >= exit_n and l[i] <= prior_low
            stop_hit = use_stop and l[i] <= stop
            if channel_hit or stop_hit:
                fills = []
                if channel_hit:
                    fills.append(o[i] if o[i] < prior_low else prior_low)
                if stop_hit:
                    fills.append(o[i] if o[i] <= stop else stop)
                fill = min(fills)
                cash = units * fill
                units = 0.0
                in_pos = False
                stop = -np.inf
                round_trip = True
        if not in_pos and not round_trip and i >= entry_n:
            atr_ok = (not use_stop) or (not np.isnan(atr[i - 1]))
            if atr_ok:
                prior_high = float(np.max(h[i - entry_n : i]))
                if h[i] > prior_high:
                    fill = o[i] if o[i] > prior_high else prior_high
                    units = cash / fill
                    cash = 0.0
                    in_pos = True
                    stop = fill - 2.0 * atr[i - 1] if use_stop else -np.inf
        equity[i] = cash + units * c[i]
        active[i] = in_pos or round_trip
    ret = np.zeros(n)
    ret[1:] = equity[1:] / equity[:-1] - 1.0
    return ret, active


def connors_rsi2(c: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Long next day after close > SMA(200) and RSI(2) < 5. Flat next day after close > SMA(5)."""
    s200 = sma(c, 200)
    s5 = sma(c, 5)
    rsi = wilder_rsi(c, 2)
    pos = np.zeros(len(c))
    in_pos = False
    for i in range(len(c) - 1):
        if not in_pos:
            if (
                not np.isnan(s200[i])
                and not np.isnan(rsi[i])
                and c[i] > s200[i]
                and rsi[i] < 5.0
            ):
                in_pos = True
        elif not np.isnan(s5[i]) and c[i] > s5[i]:
            in_pos = False
        pos[i + 1] = 1.0 if in_pos else 0.0
    return close_to_close(pos, c)


def ibs_long(h: np.ndarray, l: np.ndarray, c: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    rng = h - l
    ibs = np.where(rng > 0, (c - l) / rng, 0.5)
    pos = np.zeros(len(c))
    pos[1:] = (ibs[:-1] <= 0.2).astype(float)
    return close_to_close(pos, c)


def window_stats(
    ret: np.ndarray,
    exposed: np.ndarray,
    dts: list[datetime],
    lo: int,
    hi: int,
) -> dict:
    r = ret[lo:hi]
    exp = exposed[lo:hi]
    eq = np.cumprod(1.0 + r)
    total = float(eq[-1] - 1.0)
    peak = np.maximum.accumulate(eq)
    dd = float(np.min(eq / peak - 1.0))
    e = np.concatenate([[1.0], eq])
    trades: list[dict] = []
    start = None
    for k in range(len(exp) + 1):
        flag = bool(exp[k]) if k < len(exp) else False
        if flag and start is None:
            start = k
        if start is not None and not flag:
            end = k - 1
            pnl = float(e[end + 1] - e[start])
            ret_t = float(e[end + 1] / e[start] - 1.0)
            d0 = dts[lo + start]
            d1 = dts[lo + end]
            trades.append(
                {
                    "pnl": pnl,
                    "ret": ret_t,
                    "bars": int(end - start + 1),
                    "calendar_days": int((d1.date() - d0.date()).days) + 1,
                }
            )
            start = None
    n_tr = len(trades)
    wins = sum(1 for t in trades if t["ret"] > 0)
    gross_p = sum(t["pnl"] for t in trades if t["pnl"] > 0)
    gross_l = -sum(t["pnl"] for t in trades if t["pnl"] < 0)
    if n_tr == 0 or (gross_p == 0 and gross_l == 0):
        pf = None
    elif gross_l == 0:
        pf = None  # no losses; do not invent an infinite PF for ranking
        pf_note = "no losing trades"
    else:
        pf = float(gross_p / gross_l)
        pf_note = "account"
    if n_tr and gross_l == 0 and gross_p > 0:
        pf_note = "no losing trades"
    elif pf is not None:
        pf_note = "account"
    else:
        pf_note = "undefined"
    holds = [t["calendar_days"] for t in trades]
    span0 = dts[lo].date().isoformat()
    span1 = dts[hi - 1].date().isoformat()
    span_days = int((dts[hi - 1].date() - dts[lo].date()).days) + 1
    return {
        "from": span0,
        "to": span1,
        "span_days": span_days,
        "bars": int(hi - lo),
        "total_return": total,
        "max_dd": dd,
        "trades": n_tr,
        "win_rate": (wins / n_tr) if n_tr else None,
        "pf": pf,
        "pf_note": pf_note,
        "median_hold_days": float(np.median(holds)) if holds else None,
        "p90_hold_days": float(np.percentile(holds, 90)) if holds else None,
        "days_in_market": int(np.sum(exp)),
        "time_in_market": float(np.mean(exp)) if len(exp) else 0.0,
    }


def avg_ranks(rows: list[dict]) -> None:
    def ranks(key: str) -> list[float]:
        vals = [r[key] for r in rows]
        order = sorted(range(len(vals)), key=lambda i: (-vals[i], rows[i]["id"]))
        out = [0.0] * len(vals)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            avg = ((i + 1) + (j + 1)) / 2.0
            for k in range(i, j + 1):
                out[order[k]] = avg
            i = j + 1
        return out

    rp = ranks("pf")
    rr = ranks("total_return")
    rw = ranks("win_rate")
    for i, row in enumerate(rows):
        row["rank_pf"] = rp[i]
        row["rank_return"] = rr[i]
        row["rank_wr"] = rw[i]
        row["score"] = (rp[i] + rr[i] + rw[i]) / 3.0


def sma_up_crosses(c: np.ndarray, dts: list[datetime], lo: int, hi: int) -> int:
    m = sma(c, 150)
    n = 0
    for i in range(max(lo, 1), hi):
        if np.isnan(m[i]) or np.isnan(m[i - 1]):
            continue
        if c[i - 1] <= m[i - 1] and c[i] > m[i]:
            n += 1
    return n


def verdict(half2: dict, half1: dict, full: dict) -> str:
    """Half DD resets at the split. The -44% line uses the continuous curve."""
    if half2["trades"] < 10 or half2["pf"] is None:
        return "needs more out-of-sample"
    if (
        half2["total_return"] <= 0
        or half2["pf"] < 1
        or half2["max_dd"] < -0.44
        or full["max_dd"] < -0.44
    ):
        return "do not fund"
    h1_bad = (
        half1["total_return"] <= 0
        or half1["pf"] is None
        or half1["pf"] < 1
        or half1["trades"] < 10
    )
    if h1_bad:
        return "needs more out-of-sample"
    return "paper only"


def beats(s2: dict, base2: dict) -> dict:
    """Strict second-half beat: higher return, PF, and win rate; DD not worse; both ranked."""
    reasons = []
    if s2["trades"] < 10 or s2["pf"] is None:
        reasons.append("under 10 trades or PF undefined")
    if base2["trades"] < 10 or base2["pf"] is None:
        reasons.append("SMA150 itself under 10 trades or PF undefined")
    if s2["pf"] is None or base2["pf"] is None or not (s2["pf"] > base2["pf"]):
        reasons.append("PF not higher")
    if not (s2["total_return"] > base2["total_return"]):
        reasons.append("return not higher")
    if s2["win_rate"] is None or base2["win_rate"] is None or not (s2["win_rate"] > base2["win_rate"]):
        reasons.append("win rate not higher")
    if not (s2["max_dd"] >= base2["max_dd"]):
        reasons.append("max DD worse")
    return {"beats": len(reasons) == 0, "failed": reasons}


def main() -> None:
    ts, o, h, l, c = load()
    dts = dates_of(ts)
    gaps_h = np.diff(ts) / 3_600_000
    n = len(c)
    mid = n // 2

    series = {
        "sma150": ma_long_flat(c, 150),
        "sma200": ma_long_flat(c, 200),
        "sma50": ma_long_flat(c, 50),
        "faber10": faber_10m(c, dts),
        "tsmom12": tsmom_12_1(c, dts),
        "donchian20": breakout_long_flat(o, h, l, c, 20, 20, False),
        "turtle_s2": breakout_long_flat(o, h, l, c, 55, 20, True),
        "connors_rsi2": connors_rsi2(c),
        "ibs_long": ibs_long(h, l, c),
    }
    if tuple(series) != RULES:
        raise SystemExit("rule set drifted")

    rows = []
    for rid, (ret, exp) in series.items():
        h1 = window_stats(ret, exp, dts, 0, mid)
        h2 = window_stats(ret, exp, dts, mid, n)
        full = window_stats(ret, exp, dts, 0, n)
        rows.append(
            {"id": rid, "h1": h1, "h2": h2, "full": full, "verdict": verdict(h2, h1, full)}
        )

    base = next(r for r in rows if r["id"] == "sma150")
    eligible = [r for r in rows if r["h2"]["trades"] >= 10 and r["h2"]["pf"] is not None and r["h2"]["win_rate"] is not None]
    rank_input = []
    for r in eligible:
        rank_input.append(
            {
                "id": r["id"],
                "pf": r["h2"]["pf"],
                "total_return": r["h2"]["total_return"],
                "win_rate": r["h2"]["win_rate"],
            }
        )
    avg_ranks(rank_input)
    score = {r["id"]: r for r in rank_input}
    for r in rows:
        r["rank"] = score.get(r["id"])
        r["vs_sma150"] = beats(r["h2"], base["h2"])

    ranked = sorted(
        [r for r in rows if r["rank"]],
        key=lambda r: (r["rank"]["score"], -r["h2"]["max_dd"], r["id"]),
    )
    dropped = [r for r in rows if not r["rank"]]

    payload = {
        "data": str(DATA),
        "bars": n,
        "from": dts[0].date().isoformat(),
        "to": dts[-1].date().isoformat(),
        "median_gap_hours": float(np.median(gaps_h)),
        "min_gap_hours": float(np.min(gaps_h)),
        "max_gap_hours": float(np.max(gaps_h)),
        "split_index": mid,
        "first_half": [dts[0].date().isoformat(), dts[mid - 1].date().isoformat()],
        "second_half": [dts[mid].date().isoformat(), dts[-1].date().isoformat()],
        "sma150_up_crosses_second_half": sma_up_crosses(c, dts, mid, n),
        "sma150_up_crosses_full": sma_up_crosses(c, dts, 0, n),
        "ranked": [
            {
                "id": r["id"],
                "score": r["rank"]["score"],
                "rank_pf": r["rank"]["rank_pf"],
                "rank_return": r["rank"]["rank_return"],
                "rank_wr": r["rank"]["rank_wr"],
                "h2": r["h2"],
                "h1": r["h1"],
                "full": r["full"],
                "verdict": r["verdict"],
                "beats_sma150": r["vs_sma150"],
            }
            for r in ranked
        ],
        "unranked": [
            {
                "id": r["id"],
                "h2": r["h2"],
                "h1": r["h1"],
                "full": r["full"],
                "verdict": r["verdict"],
                "beats_sma150": r["vs_sma150"],
            }
            for r in dropped
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def pct(x: float | None) -> str:
        return "n/a" if x is None else f"{100 * x:.2f}%"

    def num(x: float | None) -> str:
        return "n/a" if x is None else f"{x:.3f}"

    print(f"bars={n} {payload['from']} -> {payload['to']} gap_h med/min/max {payload['median_gap_hours']:.2f}/{payload['min_gap_hours']:.2f}/{payload['max_gap_hours']:.2f}")
    print(f"H1 {payload['first_half']}  H2 {payload['second_half']}  SMA150 up-crosses H2={payload['sma150_up_crosses_second_half']} full={payload['sma150_up_crosses_full']}")
    print("--- RANKED ON SECOND HALF ---")
    for r in ranked:
        h2 = r["h2"]
        h1 = r["h1"]
        print(
            f"{r['id']:14} score={r['rank']['score']:.2f} "
            f"H2 ret={pct(h2['total_return'])} pf={num(h2['pf'])} wr={pct(h2['win_rate'])} "
            f"dd={pct(h2['max_dd'])} fullDD={pct(r['full']['max_dd'])} trades={h2['trades']} span={h2['span_days']}d "
            f"medHold={h2['median_hold_days']}d p90={h2['p90_hold_days']}d inMkt={h2['days_in_market']}d "
            f"| H1 ret={pct(h1['total_return'])} pf={num(h1['pf'])} wr={pct(h1['win_rate'])} "
            f"dd={pct(h1['max_dd'])} trades={h1['trades']} "
            f"| {r['verdict']} beats={r['vs_sma150']['beats']} {r['vs_sma150']['failed']}"
        )
    print("--- UNRANKED (<10 trades or PF undefined on H2) ---")
    for r in dropped:
        h2 = r["h2"]
        h1 = r["h1"]
        print(
            f"{r['id']:14} H2 ret={pct(h2['total_return'])} pf={num(h2['pf'])}({h2['pf_note']}) "
            f"wr={pct(h2['win_rate'])} dd={pct(h2['max_dd'])} fullDD={pct(r['full']['max_dd'])} trades={h2['trades']} "
            f"span={h2['span_days']}d medHold={h2['median_hold_days']} inMkt={h2['days_in_market']}d "
            f"| H1 ret={pct(h1['total_return'])} pf={num(h1['pf'])} wr={pct(h1['win_rate'])} "
            f"dd={pct(h1['max_dd'])} trades={h1['trades']} | {r['verdict']}"
        )


if __name__ == "__main__":
    main()
