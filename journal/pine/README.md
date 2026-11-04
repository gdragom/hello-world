# LEDGER Pine

| File | Role |
|------|------|
| `LEDGER_ICT_Setup_v0.1.pine` | Indicator — chart / alerts |
| `LEDGER_ICT_Strategy_v0.6.pine` | Strategy **both sides** v0.8.8 |
| `LEDGER_ICT_Strategy_Long.pine` | BTC Strategy **LONG only** v0.9.16 (SMA 7/14 ON, FVG **or** OB, Fixed $500/$1100) |
| `LEDGER_ICT_Strategy_Long_v0.9.8.pine` | BTC Long **v0.9.8 snapshot** — Deep pack, **no SMA gate**, FVG **or** OB, IFVG@6, Fixed $500/$1000 |
| `LEDGER_ICT_Strategy_Short.pine` | BTC Strategy **SHORT only** v0.9.16 (SMA 7/14 ON, FVG **or** OB, Fixed $500/$1100) |
| `LEDGER_ICT_Strategy_Long_Gold.pine` | **XAUUSD LONG** v0.1 (Custom pack) |
| `LEDGER_ICT_Strategy_Short_Gold.pine` | **XAUUSD SHORT** v0.1 (Custom pack) |
| `../tools/optimize_ledger.py` | Local grid / walk-forward |

## Webhook → Bitget (v0.9.6 / Gold v0.1)

LEDGER sizes live orders from env: 100 USDT × 20x, SL/TP **5%/10% of that USDT balance** ($5 / $10). See [`../../docs/TV-WEBHOOK.md`](../../docs/TV-WEBHOOK.md).

## Gold default pack (v0.1)

Same ICT rules as BTC; **Custom** preset defaults. Chart: **XAUUSD 1H**.

| Knob | Value |
|------|--------|
| Preset | Custom (manual) |
| Doji body | **10%** |
| Bias | **Aligned only** |
| Structure | **Any** · swing **8** · min **0.6×ATR** · ATR **14** |
| Fib | **Immediate on BOS** |
| Entry | **Zone + FVG/OB** · virgin keep **60** |
| Re-entry | ON · cooldown **10** · post-stop **10** |
| LTF IFVG | ON · TF **5m** · max age **12** |
| Long SL/TP | **$100 / $150** (RR 1.5; grid best, still weak PF) |
| Short SL/TP | **$100 / $200** (RR 2; grid best) |

**SL/TP grid** (`tools/optimize_gold_sltp.py` on Bitget `XAUUSDT`, Custom pack locked, 5m IFVG): search ~2026-02→07 + 90d holdout. Short wins clearly; Long least-bad is $100/$150 but search PF&lt;1. Excel: `tools/out/gold_sltp_*.xlsx`.

## BTC Long defaults (v0.9.16)

Chart TF **1H**. Defaults = your TV Inputs screenshots.

| Knob | Long default |
|------|--------------|
| Lab | Use Settings knobs **OFF** · Preset **Custom** |
| Doji / Bias | **10%** · **Aligned only** |
| HTF SMA | **ON** · fast **7** / slow **14** |
| Structure | **Any** · swing **8** · **0.6×ATR** · Immediate |
| Entry | **Zone + FVG or OB** · zoneKeep **80** · cool **10/10** |
| LTF | 5m IFVG age **6** · wick ≤0.5 |
| Exits | Fixed **SL $500** · risk **$500** · TP **$1100** |

**Short v0.9.16:** same pack as Long · only short if daily close **<** SMA 7 and 14 · Fixed **$500 / $1100**.
Live Bitget: see [`../../docs/TV-WEBHOOK.md`](../../docs/TV-WEBHOOK.md).
Panel: `0.9.16 LONG` / `0.9.16 SHORT`.

## Optimizer

See [`../tools/README.md`](../tools/README.md).
