#!/usr/bin/env bash
# Install & run LEDGER (Next.js journal) on Ubuntu Raspberry Pi.
# Usage:
#   cd hello-world
#   git checkout cursor/pi-wireguard-vpn-e86f   # or master once merged
#   chmod +x journal/deploy/pi-setup.sh
#   ./journal/deploy/pi-setup.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
JOURNAL="${ROOT}/journal"
SERVICE_SRC="${JOURNAL}/deploy/ledger.service"
SERVICE_DST="/etc/systemd/system/ledger.service"

echo "==> LEDGER Pi setup"
echo "    repo: ${ROOT}"
echo "    app:  ${JOURNAL}"

if [[ ! -f "${JOURNAL}/package.json" ]]; then
  echo "journal/package.json not found. Clone the repo and checkout the branch with journal/."
  exit 1
fi

# Node 22 LTS
if ! command -v node >/dev/null 2>&1 || [[ "$(node -v | sed 's/v//;s/\..*//')" -lt 20 ]]; then
  echo "==> Installing Node.js 22"
  curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
  sudo apt-get install -y nodejs
fi
echo "==> Node $(node -v) / npm $(npm -v)"

cd "${JOURNAL}"

if [[ ! -f .env.local ]]; then
  cp .env.example .env.local
  echo "==> Created journal/.env.local — edit it before starting:"
  echo "    nano ${JOURNAL}/.env.local"
  echo "    Required for live Bitget: BITGET_API_KEY, BITGET_SECRET_KEY, BITGET_PASSPHRASE"
  echo "    Recommended: SITE_PASSWORD=..."
  echo "    R2_* optional on Pi (local journal/data is used without R2)"
fi

mkdir -p data
echo "==> npm install"
npm install

echo "==> npm run build"
npm run build

# systemd unit with correct User + WorkingDirectory
USER_NAME="$(id -un)"
HOME_DIR="$(getent passwd "${USER_NAME}" | cut -d: -f6)"
NODE_BIN="$(command -v node)"
npm_BIN="$(command -v npm)"

TMP_UNIT="$(mktemp)"
sed \
  -e "s|__USER__|${USER_NAME}|g" \
  -e "s|__JOURNAL__|${JOURNAL}|g" \
  -e "s|__NODE__|${NODE_BIN}|g" \
  -e "s|__NPM__|${npm_BIN}|g" \
  "${SERVICE_SRC}" >"${TMP_UNIT}"

echo "==> Installing systemd service (ledger.service)"
sudo cp "${TMP_UNIT}" "${SERVICE_DST}"
rm -f "${TMP_UNIT}"
sudo systemctl daemon-reload
sudo systemctl enable ledger.service
sudo systemctl restart ledger.service

sleep 2
sudo systemctl --no-pager --full status ledger.service || true

LAN_IP="$(hostname -I | awk '{print $1}')"
echo
echo "============================================"
echo " LEDGER should be running on port 3000"
echo "============================================"
echo " On home Wi-Fi:     http://${LAN_IP}:3000"
echo " Over WireGuard:    http://10.8.0.1:3000"
echo "                    (or http://${LAN_IP}:3000 while VPN is on)"
echo
echo " Edit env:  nano ${JOURNAL}/.env.local"
echo " Then:      sudo systemctl restart ledger"
echo
echo " Logs:      journalctl -u ledger -f"
echo " Status:    sudo systemctl status ledger"
