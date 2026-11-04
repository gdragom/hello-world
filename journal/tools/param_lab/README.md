# LEDGER Param lab

Local backtest explorer for **Long** and **Short** Custom knobs (no chart).

## Run

```bash
cd journal/tools/param_lab
python serve.py
```

Opens [http://127.0.0.1:8766](http://127.0.0.1:8766).

## Use

1. Pick **Long** or **Short** (defaults SL/TP: Long $500/$1000, Short $1000/$2000).
2. Toggle chips (multi-select = grid axes).
3. **Run selected** = one combo · **Run grid** = cartesian product (max 216).
4. Sort table by PF / WR / PnL% / DD / Score.

Uses Bitget CSVs under `journal/tools/data/` and the shared `ledger_engine` (Long entries ≈ TV-synced). Confirm top combos on TradingView before going live.
