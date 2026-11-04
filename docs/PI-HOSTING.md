# LEDGER journal on Raspberry Pi

TradingView needs a public **HTTPS** webhook. Run Next.js on the Pi, expose `/api/tv-webhook` via Tailscale Funnel or Cloudflare Tunnel.

## One-time SSH (from Windows)

Pi LAN IP (this desk): `192.168.68.57` · user **`max`**.

```powershell
ssh quant-pi
```

`~/.ssh/config` Host `quant-pi` → `max@192.168.68.57` with `id_ed25519_quant_pi`.

## Install / update

```bash
# On Pi
cd ~
git clone https://github.com/gdragom/hello-world.git   # or: git pull
cd hello-world/journal
bash deploy/pi/setup.sh
```

Copy secrets (from Windows, after SSH works):

```powershell
scp -i $env:USERPROFILE\.ssh\id_ed25519_quant_pi `
  c:\Users\user\OneDrive\hello-world\journal\.env.local `
  quant-pi:~/hello-world/journal/.env.local
```

Ensure `.env.local` on Pi has:

- Bitget keys
- `TV_WEBHOOK_SECRET` (same as Pine)
- `BITGET_EXECUTE=dry_run` first, then `live`
- sizing pack: `BITGET_SL_PCT=5`, `BITGET_TP_PCT=11`, `BITGET_TARGET_SL_USD=500`, `BITGET_TARGET_TP_USD=1100`

## HTTPS for TradingView

Pick one:

**Tailscale Funnel** (if Tailscale is on the Pi):

```bash
sudo tailscale funnel --bg 3000
# → https://<magicdns>/api/tv-webhook
```

**Cloudflare Tunnel**:

```bash
cloudflared tunnel --url http://127.0.0.1:3000
```

Point TV alerts (Long + Short) at that URL + `/api/tv-webhook`.

## Prove → live

```bash
curl -X POST https://YOUR_PI_HTTPS/api/tv-webhook \
  -H 'Content-Type: application/json' \
  -d '{"secret":"YOUR_SECRET","stage":"ENTRY_READY","action":"enter","symbol":"BTCUSDT","side":"long","timeframe":"60","price":100000,"entry":100000,"sl":99500,"tp":101100,"qty":0.01,"orderType":"market","clientOid":"pi-dry-1","message":"pi dry"}'
```

Expect `exec.mode: dry_run`, qty ~`0.01`–`0.02`, lev ~`10`, risk ~5% of tier.

Then: set `BITGET_EXECUTE=live` in `.env.local`, `sudo systemctl restart ledger-journal`.
