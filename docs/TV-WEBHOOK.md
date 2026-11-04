# TradingView → LEDGER → Bitget

LEDGER receives TradingView strategy alerts, shows them on the dashboard, optionally pushes Telegram, and can place **USDT-FUTURES** orders on Bitget (qty / price / SL / TP / trailing) — without using Bitget’s signal bot.

## Endpoint

```
POST https://ledger-ict-journal.vercel.app/api/tv-webhook
```

If `SITE_PASSWORD` is set, this path stays public (middleware allowlist). Protect it with `TV_WEBHOOK_SECRET`.

## Flow

```
Pine strategy alert (ENTRY_READY + entry/sl/tp/qty)
  → /api/tv-webhook (secret check)
  → alert store + Telegram
  → maybeExecuteBitget (off | dry_run | live)
```

## Pine setup (v0.9.8 Long / v0.9.9 Short)

1. Paste `LEDGER_ICT_Strategy_Long.pine` or `…_Short.pine` on BTCUSDT.P **1H**.
2. Set **TV_WEBHOOK_SECRET** input to the same value as Vercel `TV_WEBHOOK_SECRET`.
3. Create alert → condition **Any alert() function call** → Webhook URL = endpoint above.
4. Message body can stay empty (Pine `alert()` already sends JSON).

### ENTRY_READY payload (auto from Pine)

```json
{
  "secret": "YOUR_TV_WEBHOOK_SECRET",
  "stage": "ENTRY_READY",
  "action": "enter",
  "symbol": "BTCUSDT",
  "side": "short",
  "timeframe": "60",
  "price": 95000,
  "entry": 95000,
  "sl": 96000,
  "tp": 93000,
  "qty": 0.5,
  "riskUsd": 500,
  "orderType": "market",
  "clientOid": "es1728000000000",
  "trail": false,
  "confidence": 70,
  "bias": "bear",
  "message": "ENTRY short qty=0.5 …"
}
```

Optional trail fields when Pine **Include trailing stop** is on:

- `trail`: true  
- `trailActivate`: price  
- `trailRatio`: pullback % (Bitget `trailVariance`)

### SETUP_ARMED / INVALID

Still supported for dashboard / Telegram only (no Bitget order).

## Bitget execute modes

| `BITGET_EXECUTE` | Behavior |
|------------------|----------|
| `off` (default) | Alerts only — safe |
| `dry_run` | Build order JSON (`exec.plan` + `exec.order`); **no** Bitget call |
| `live` | `setLeverage` + `placeOrder` with SL/TP |

### Status (what’s built)

| Piece | State |
|-------|--------|
| Pine `alert()` ENTRY_READY JSON | Done (Long / Short) |
| `POST /api/tv-webhook` + secret | Done |
| Dashboard / Telegram / Discord | Done |
| Bitget size + SL/TP + `placeOrder` | Done (`off` / `dry_run` / `live`) |
| Live USDT equity fetch each alert | Done |
| $100 account = 1/100 of TV Fixed ($500 risk / $1100 TP), ~10x | Done |

**Not done until you deploy:** Pi/Vercel host, env secrets, TV alert webhook URL, `dry_run` proof, then `live`.

### Live pack ($100 account)

TV Fixed on **$10k**: cash risk **$500**, cash TP **$1100**, price SL distance **$500** (qty 1).  
Live on **$100**: same prices, **5% / 11%** of equity → cash **$5 / $11**, qty **0.01**, leverage ~**10x**.

```bash
BITGET_EXECUTE=dry_run
BITGET_SYMBOL_ALLOWLIST=BTCUSDT
BITGET_MARGIN_USDT=0
BITGET_ACCOUNT_USDT=100
BITGET_SIZE_MIN=100
BITGET_SIZE_STEP=100
BITGET_SL_PCT=5
BITGET_TP_PCT=11
BITGET_TARGET_RISK_USD=0
BITGET_TARGET_REWARD_USD=0
BITGET_TARGET_SL_USD=500
BITGET_TARGET_TP_USD=1100
BITGET_LEVERAGE_MAX=20
BITGET_MAX_QTY=5
```

| BTC price | $10k cash SL/TP | $100 cash SL/TP | Lev |
|-----------|-----------------|-----------------|-----|
| $100k | $500 / $1100 | **$5 / $11** | **~10x** |

`TARGET_RISK/REWARD=0` means size from `SL_PCT` / `TP_PCT` × wallet tier. Alert `sl`/`tp` prices still win when present.

### Env (Vercel / Pi `.env.local`)

```bash
TV_WEBHOOK_SECRET=...
BITGET_API_KEY=...
BITGET_SECRET_KEY=...
BITGET_PASSPHRASE=...

BITGET_EXECUTE=dry_run
BITGET_SYMBOL_ALLOWLIST=BTCUSDT
BITGET_MARGIN_USDT=0
BITGET_ACCOUNT_USDT=100
BITGET_SIZE_MIN=100
BITGET_SIZE_STEP=100
BITGET_SL_PCT=5
BITGET_TP_PCT=11
BITGET_TARGET_RISK_USD=0
BITGET_TARGET_REWARD_USD=0
BITGET_TARGET_SL_USD=500
BITGET_TARGET_TP_USD=1100
BITGET_LEVERAGE=10
BITGET_LEVERAGE_MAX=20
BITGET_MAX_QTY=5
BITGET_ALLOW_PYRAMID=0
```

Each `ENTRY_READY` fetches Bitget USDT equity, floors to the tier, recomputes qty / SL / TP / lev.

Use a Bitget API key with **futures trade** permission only when you switch to `live`. Prefer demo/paper keys first.

### Rollout checklist (Long + Short)

1. **Bitget** — Fund futures wallet **$100 USDT**. Create API key (futures trade; IP-restrict to Pi/Vercel).
2. **Host LEDGER** — Pi or Vercel; copy `.env.example` → `.env.local` with the pack above; `BITGET_EXECUTE=dry_run` first. HTTPS URL required for TV (Cloudflare Tunnel / Tailscale Funnel / Vercel).
3. **Pine Long / Short** — Paste current Fixed pack on **BTCUSDT.P 1H**: SL $500 / risk $500 / TP $1100. Set **TV_WEBHOOK_SECRET**.
4. **TV alerts** — Each strategy: condition **Any alert() function call** → Webhook URL `https://YOUR_HOST/api/tv-webhook`. Message body empty.
5. **Dry-run proof** — Wait for an alert or POST a test `ENTRY_READY` JSON. Plan should show ~qty `0.01`, lev ~`10`, cash risk ~`$5`.
6. **Go live** — Set `BITGET_EXECUTE=live`, restart / redeploy.

## Discord

Channel → Edit channel → Integrations → Webhooks → New Webhook → Copy URL:

```bash
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

Same alert text as Telegram (embed). Works with Telegram side-by-side; either can be unset.

## Safety

- Secret required when `TV_WEBHOOK_SECRET` is set  
- Symbol allowlist  
- Max qty cap  
- Skip if open position (unless pyramid allowed)  
- `clientOid` idempotency (~dedupe TV retries)  
- Preset SL/TP on the entry order; trailing is optional strategy order  

## Manual curl test (dry_run)

```bash
curl -X POST https://YOUR_DOMAIN/api/tv-webhook \
  -H "Content-Type: application/json" \
  -d '{"secret":"YOUR_SECRET","stage":"ENTRY_READY","action":"enter","symbol":"BTCUSDT","side":"short","timeframe":"60","price":95000,"entry":95000,"sl":96000,"tp":93000,"qty":0.01,"orderType":"market","clientOid":"test001","message":"manual dry"}'
```

Response includes `exec.order` when `BITGET_EXECUTE=dry_run`.
