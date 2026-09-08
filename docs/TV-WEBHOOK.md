# TradingView → LEDGER webhook

LEDGER receives TradingView Premium alerts and shows them on the dashboard.
Optional Telegram push uses the same payload.

## Endpoint

```
POST https://ledger-ict-journal.vercel.app/api/tv-webhook
```

If `SITE_PASSWORD` is set, this path is still public (webhook must work without cookies).
Protect it with `TV_WEBHOOK_SECRET`.

## Alert message (JSON)

Create two alerts on TradingView.

### 1H — SETUP_ARMED

When 1H ERL sweep + body MSS + Fib 0.5 IRL (+ FVG/OB) is ready:

```json
{
  "secret": "YOUR_TV_WEBHOOK_SECRET",
  "stage": "SETUP_ARMED",
  "symbol": "{{ticker}}",
  "side": "long",
  "timeframe": "60",
  "price": {{close}},
  "message": "1H MSS + IRL below 0.5 — wait 5m CISD/MSS"
}
```

Use `"side": "short"` on the bearish alert. Put your real secret string in `secret`.

### 5m — ENTRY_READY

When LTF CISD or MSS prints inside IRL:

```json
{
  "secret": "YOUR_TV_WEBHOOK_SECRET",
  "stage": "ENTRY_READY",
  "symbol": "{{ticker}}",
  "side": "long",
  "timeframe": "5",
  "price": {{close}},
  "message": "5m CISD/MSS in IRL — entry candidate"
}
```

### INVALID (optional)

```json
{
  "secret": "YOUR_TV_WEBHOOK_SECRET",
  "stage": "INVALID",
  "symbol": "{{ticker}}",
  "side": "long",
  "timeframe": "60",
  "price": {{close}},
  "message": "structure broken"
}
```

## TradingView UI

1. Condition → your Pine / drawing-based alert
2. Notifications → **Webhook URL** = `https://…/api/tv-webhook`
3. Message = one of the JSON bodies above (not the default `{{strategy…}}` only)

Header alternative: `x-ledger-secret: YOUR_TV_WEBHOOK_SECRET`

## Telegram

1. Talk to `@BotFather`, get `TELEGRAM_BOT_TOKEN`
2. Message your bot, then get `TELEGRAM_CHAT_ID` (e.g. via `@userinfobot` or `getUpdates`)
3. Set both on Vercel env and redeploy

## Stages

| stage | meaning |
|-------|---------|
| `SETUP_ARMED` | 1H checklist ready — watch 5m |
| `ENTRY_READY` | 5m CISD/MSS — entry candidate (not “must enter”) |
| `INVALID` | setup expired |
