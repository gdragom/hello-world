# LEDGER tools

## TradingView strategy v0.8.0

File: `../pine/LEDGER_ICT_Strategy_v0.6.pine`

| Feature | Default / notes |
|---------|-----------------|
| Date window | **ON** · 2024-09 → 2026-09 (recent ~2y). Turn off only for stress tests |
| Post-stop ban | 6–12 bars after losing exit (preset C = 8) |
| Min hold | First N bars TP-only (C = 4) — cuts 1-bar stop churn |
| Short filter | C: **No shorts on bull day** · A/B: **Aligned only** |
| BE after R | ON · move SL → entry when MFE ≥ 1R |
| Same-Fib reenter | Off on A/B/C (D only) |

## Python optimizer

Approximate port of the 1H strategy for **grid + tune/confirm + walk-forward**.  
Rank in Python → confirm on TV. Default eval = **last 2 years**, tune last 365d, confirm prior 365d.

### Setup

```bash
cd journal/tools
pip install -r requirements-opt.txt
```

### Tune + confirm (recommended)

```bash
python optimize_ledger.py --csv data/btcusdt_1h.csv --quick --recent-years 2 --tune-days 365
```

### Walk-forward on recent 2y

```bash
python optimize_ledger.py --csv data/btcusdt_1h.csv --walkforward --quick --recent-years 2 --windows 4
```

Outputs: `journal/tools/out/*.csv`.

### TV ↔ Python visual compare (2026→now)

```bash
cd journal/tools/parity_viz
python serve.py
```

Opens http://127.0.0.1:8765 — Bitget 1H candles with Python fib/FVG overlays and TV vs Python entry markers. See `parity_viz/README.md`.

### Param lab (Long / Short knobs → PF WR PnL DD)

```bash
cd journal/tools/param_lab
python serve.py
```

Opens http://127.0.0.1:8766 — toggle ATR/swing/bias/wick/IFVG etc., run one backtest or a grid, sort by metrics. See `param_lab/README.md`.

### Map CSV → TV Custom

| CSV | TV input |
|-----|----------|
| swing_len | Swing pivot length |
| min_swing_atr | Min swing × ATR |
| fib_mode immediate/wait | Fib timing |
| entry_mode deep | FVG/OB or deep zone |
| entry_mode zone_fvg_ob | Zone + FVG/OB |
| bias_filter | Bias filter (longs) |
| short_filter no_bull | No shorts on bull day |
| short_filter aligned | Short filter = Aligned only |
| short_filter long_only | Long only |
| post_stop_cooldown | Post-stop ban (bars) |
| be_trigger_r | BE trigger (R); 0 = off |
| min_hold_bars | Min hold before SL |
| rr_mult | Take profit (R) |
