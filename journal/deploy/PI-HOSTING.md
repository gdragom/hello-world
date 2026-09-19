# Host LEDGER on Raspberry Pi (replace Vercel)

Run the Next.js journal on your Pi. Access it over home LAN or WireGuard VPN — no AWS/Azure/Vercel required.

## Why Pi is nicer than Vercel for this app

| Vercel | Pi |
|--------|----|
| Ephemeral disk → needed Cloudflare R2 | Data stays in `journal/data/` |
| Public URL needs `SITE_PASSWORD` | VPN-only access is enough (password still recommended) |
| Cold starts / usage limits | Always on at home |

R2 is **optional** on Pi. Without `R2_*`, screenshots fall back to inline `dataUrl` and JSON is stored under `journal/data/`.

## One-time setup (on the Pi)

```bash
sudo apt update
sudo apt install -y git curl

git clone https://github.com/gdragom/hello-world.git
cd hello-world
git checkout cursor/pi-wireguard-vpn-e86f   # branch with journal + Pi deploy

chmod +x journal/deploy/pi-setup.sh
./journal/deploy/pi-setup.sh
```

Edit secrets **before** or right after first run:

```bash
nano journal/.env.local
```

Minimum for live Bitget sync:

```env
BITGET_API_KEY=...
BITGET_SECRET_KEY=...
BITGET_PASSPHRASE=...
SITE_PASSWORD=pick-a-password
JOURNAL_FORCE_DEMO=0
```

Then:

```bash
sudo systemctl restart ledger
```

## Open from iPhone

1. Connect **Shadowrocket** (WireGuard or VLESS profile for `max-trading.duckdns.org`)
2. Safari → `http://10.8.0.1:3000`  
   (or your Pi LAN IP, e.g. `http://192.168.x.x:3000`)

Do **not** port-forward 3000 on Deco unless you intentionally want it public.
Port **443** is reserved for VLESS — keep the journal private behind VPN.

## Useful commands

```bash
sudo systemctl status ledger
sudo systemctl restart ledger
journalctl -u ledger -f

cd ~/hello-world/journal
git pull
npm install
npm run build
sudo systemctl restart ledger
```

## TradingView webhooks

TV alerts need a public HTTPS URL. Options later:

1. Keep webhook on Vercel temporarily, or  
2. Port-forward + Caddy/HTTPS + DuckDNS, or  
3. Cloudflare Tunnel  

VPN alone is enough for **you** using the dashboard; webhooks are separate.

## Stop using Vercel (optional)

When Pi is stable:

1. Pause/delete the Vercel project  
2. Disable `.github/workflows/deploy-journal.yml` or remove the workflow  
3. Point bookmarks to the Pi URL over VPN  

Export any important R2 JSON first if you relied on cloud storage (`app-data/journal.json`, etc.) into `journal/data/`.
