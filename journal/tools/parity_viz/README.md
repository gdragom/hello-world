# LEDGER TV ↔ Python parity visualizer

Local chart to compare **Python fib / 1H FVG / entries** against your **TradingView List of Trades** export (2026 → now).

## Run

```bash
cd journal/tools/parity_viz
python serve.py
```

Opens [http://127.0.0.1:8765](http://127.0.0.1:8765).

Rebuild data only:

```bash
python build_data.py
```

## What you see

| Overlay | Source |
|--------|--------|
| Candles | Bitget 1H CSV |
| Gold / teal lines | Python fib 0.5 + zone floor |
| Green bands | Python 1H bullish FVG boxes |
| Blue triangles | TV-only entries |
| Orange triangles | Python-only entries |
| Green diamonds | Same UTC hour on both |

Click a trade in the side list to zoom ± a few days.

## Notes

- Fib/FVG drawings are **Python only** (TV export has no structure objects).
- TV times are parsed as chart timezone `America/New_York` → UTC (same as the diff script).
- Config matches the Custom screenshot stack used in `parity_tv_last365.py`.
