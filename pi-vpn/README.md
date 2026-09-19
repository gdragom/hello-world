# Raspberry Pi WireGuard VPN (Shadowrocket)

Sets up a WireGuard server on Ubuntu so your iPhone (Shadowrocket) can reach home from anywhere.

## On the Pi

```bash
# copy setup-wireguard.sh to the Pi, then:
sudo apt update
chmod +x setup-wireguard.sh
sudo ./setup-wireguard.sh
```

If public IP detection fails:

```bash
SERVER_PUBLIC_IP=YOUR.PUBLIC.IP sudo -E ./setup-wireguard.sh
```

## Router

1. Give the Pi a **DHCP reservation** (fixed LAN IP)
2. Port forward: **UDP 51820 → Pi LAN IP : 51820**
3. If your ISP uses **CGNAT**, port forward will not work from the internet — use Tailscale instead, or a cheap VPS relay

## iPhone (Shadowrocket)

1. Get `/etc/wireguard/clients/iphone.conf` from the Pi  
   ```bash
   sudo cat /etc/wireguard/clients/iphone.conf
   ```
2. Shadowrocket → **+** → type **WireGuard** → paste/import config  
   (Or use the official WireGuard iOS app and scan the QR the script prints)
3. Turn the profile **on**
4. Test on **cellular data** (turn Wi‑Fi off)

## Useful commands (Pi)

```bash
sudo wg show
sudo systemctl status wg-quick@wg0
sudo systemctl restart wg-quick@wg0
```

## Add another device later

```bash
CLIENT_NAME=laptop sudo -E ./setup-wireguard.sh
# Note: re-running regenerates only missing keys; edit wg0.conf peers manually
# for multiple clients, or ask for an add-peer helper.
```

## After VPN works

Host LEDGER journal on the Pi and open `http://10.8.0.1:3000` (or Pi LAN IP) from the phone while VPN is connected — no public web exposure required.
