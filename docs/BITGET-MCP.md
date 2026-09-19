# Bitget MCP + LEDGER journal

Official package (also listed on [cursor.directory/plugins/bitget-mcp-server](https://cursor.directory/plugins/bitget-mcp-server)):

```bash
npx -y @bitget-ai/bitget-agent-mcp --read-only
```

## Cursor setup (recommended for this repo)

1. Copy the example config:
   ```bash
   cp .cursor/mcp.json.example .cursor/mcp.json
   ```
2. Replace `REPLACE_ME` with your Bitget API credentials  
   (same three values Bitget shows as API Key / Secret Key / Passphrase).
3. Restart Cursor MCP / reload the window.
4. Ask: **“What Bitget tools are available?”**  
   You should see intent verbs like `market`, `position`, `order`, plus `discover` and `raw`.

### Env vars (official MCP names)

| Variable | Notes |
|----------|--------|
| `BITGET_API_KEY` | required for private reads |
| `BITGET_SECRET_KEY` | official name (LEDGER also accepts legacy `BITGET_API_SECRET`) |
| `BITGET_PASSPHRASE` | also accepts legacy `BITGET_API_PASSPHRASE` |

### Safety for journaling

This repo’s example uses **`--read-only`** so Cursor can pull balances, position history, and candles, but **cannot place/cancel orders**. For demo funds instead, swap to `--paper-trading` + Demo API keys.

## How this pairs with LEDGER

| Surface | Role |
|---------|------|
| **Bitget MCP in Cursor** | Chat with the agent: “지난 BTC 포지션 히스토리 가져와”, “15m 캔들 보여줘”, 복기 토론 |
| **LEDGER web app (`journal/`)** | Dashboard UI: chart markers, notes, rule checklist, weekly review |

Both use the **same credentials** and the official **UTA v3** stack (`@bitget-ai/bitget-agent-sdk` under the hood for LEDGER sync).

LEDGER `.env.local` example:

```bash
BITGET_API_KEY=...
BITGET_SECRET_KEY=...
BITGET_PASSPHRASE=...
DEFAULT_RISK_USD=25
```

Then open the app and click **Sync Bitget**.

## Useful MCP prompts for your ICT journal

- `discover({ domain: "trade" })` then pull position history for BTCUSDT
- “List my closed BTC USDT-FUTURES positions from the last 30 days”
- “Get 15m BTCUSDT candles around this open/close time”
- After pasting a LEDGER review: “이 트레이드에서 2R 전 반익절 위반이 있었는지 같이 보자”
