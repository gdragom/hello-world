#!/usr/bin/env bash
# One-shot remote access stack for max-trading.duckdns.org
# Order: DuckDNS → refresh WireGuard Endpoint → VLESS Reality backup
#
#   cd ~/hello-world/pi-vpn
#   cp secrets.env.example secrets.env && nano secrets.env  # add DUCKDNS_TOKEN
#   sudo ./setup-remote-access.sh
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo $0"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "${SCRIPT_DIR}"

if [[ ! -f secrets.env ]]; then
  cp secrets.env.example secrets.env
  echo "Created ${SCRIPT_DIR}/secrets.env — add DUCKDNS_TOKEN then re-run."
  echo "  nano ${SCRIPT_DIR}/secrets.env"
  exit 1
fi

# shellcheck disable=SC1091
set -a
source "${SCRIPT_DIR}/secrets.env"
set +a

if [[ -z "${DUCKDNS_TOKEN:-}" ]]; then
  echo "DUCKDNS_TOKEN is empty in secrets.env"
  exit 1
fi

chmod +x setup-duckdns.sh setup-wireguard.sh setup-vless.sh

echo "======== 1/3 DuckDNS ========"
./setup-duckdns.sh

if [[ ! -f /etc/wireguard/wg0.conf ]]; then
  echo "======== 2/3 WireGuard (fresh install) ========"
  ./setup-wireguard.sh
else
  echo "======== 2/3 WireGuard already installed — Endpoint updated by DuckDNS step ========"
  systemctl restart wg-quick@wg0 || true
  wg show || true
fi

echo "======== 3/3 VLESS + Reality ========"
./setup-vless.sh

cat <<EOF

============================================
 Remote access stack ready
============================================
 Hostname: max-trading.duckdns.org  (or \$DUCKDNS_DOMAIN)

 Deco port forwards needed:
   UDP 51820 → Pi   (WireGuard)
   TCP 443   → Pi   (VLESS)

 Shadowrocket:
   Profile A: WireGuard  sudo cat /etc/wireguard/clients/iphone.conf
   Profile B: VLESS      sudo cat /usr/local/etc/xray/vless-shadowrocket.txt

 LEDGER (next):
   cd ~/hello-world && ./journal/deploy/pi-setup.sh
   Phone + VPN → http://10.8.0.1:3000
EOF
