# Raspberry Pi remote access: DuckDNS + WireGuard + VLESS

Hostname used in these scripts: **`max-trading.duckdns.org`**

## Security first

If your DuckDNS **token** appeared in a screenshot or chat, open https://www.duckdns.org and **regenerate / use a new token** before saving it on the Pi. Never commit `secrets.env` to git.

## One-shot (recommended)

On the Pi:

```bash
cd ~
git clone https://github.com/gdragom/hello-world.git
cd hello-world
git checkout cursor/pi-wireguard-vpn-e86f
git pull

cd pi-vpn
cp secrets.env.example secrets.env
nano secrets.env   # set DUCKDNS_TOKEN=...  (domain already max-trading)

chmod +x setup-*.sh
sudo ./setup-remote-access.sh
```

## Shadowrocket QR codes (no typing)

On the Pi:

```bash
cd ~/hello-world/pi-vpn
git pull
chmod +x make-shadowrocket-qrs.sh
sudo ./make-shadowrocket-qrs.sh
```

Scan the two terminal QR codes with Shadowrocket (**+ → Scan QR Code**):
1. **WireGuard** = Profile A  
2. **VLESS** = Profile B  

PNG copies are saved under `pi-vpn/qrcodes/` if you prefer scanning from the Pi desktop image viewer.

## Deco port forwards

| Protocol | Port | To |
|----------|------|-----|
| **UDP** | 51820 | Pi LAN IP (WireGuard) |
| **TCP** | 443 | Pi LAN IP (VLESS) |

Keep Pi DHCP reservation as you already did.

## Shadowrocket

**Profile A — WireGuard**
```bash
sudo cat /etc/wireguard/clients/iphone.conf
```
Endpoint should be `max-trading.duckdns.org:51820`.

**Profile B — VLESS (China / UDP-blocked networks)**
```bash
sudo cat /usr/local/etc/xray/vless-shadowrocket.txt
```
Import the `vless://...` link in Shadowrocket.

## LEDGER journal (local storage, no Cloudflare R2)

```bash
cd ~/hello-world
./journal/deploy/pi-setup.sh
nano journal/.env.local   # Bitget keys + SITE_PASSWORD; leave R2_* empty
sudo systemctl restart ledger
```

On phone with VPN/VLESS connected: `http://10.8.0.1:3000`  
Do **not** put the journal on public port 443 (that port is for VLESS).

## Scripts

| Script | Purpose |
|--------|---------|
| `setup-duckdns.sh` | Cron updater + rewrite WG Endpoint |
| `setup-wireguard.sh` | WG server; Endpoint defaults to DuckDNS |
| `setup-vless.sh` | Xray VLESS + Reality on TCP 443 |
| `setup-remote-access.sh` | Runs the three above in order |
