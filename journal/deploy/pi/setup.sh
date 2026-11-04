#!/usr/bin/env bash
# Run on the Pi from journal/: bash deploy/pi/setup.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

if [[ ! -f .env.local ]]; then
  echo "Missing .env.local — copy from Windows or .env.example first." >&2
  exit 1
fi

if ! command -v node >/dev/null; then
  echo "Installing Node 22 via NodeSource…"
  curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
  sudo apt-get install -y nodejs
fi

echo "==> node $(node -v) npm $(npm -v)"
npm ci
npm run build

UNIT_SRC="$ROOT/deploy/pi/ledger-journal.service"
UNIT_DST=/etc/systemd/system/ledger-journal.service
# Rewrite WorkingDirectory / User if not classic pi home
USER_NAME="$(whoami)"
HOME_DIR="$HOME"
sed -e "s|/home/pi/hello-world/journal|$ROOT|g" \
    -e "s|^User=pi$|User=$USER_NAME|g" \
    "$UNIT_SRC" | sudo tee "$UNIT_DST" >/dev/null

sudo systemctl daemon-reload
sudo systemctl enable ledger-journal
sudo systemctl restart ledger-journal
sudo systemctl --no-pager status ledger-journal || true

echo "SETUP_DONE — local: http://$(hostname -I | awk '{print $1}'):3000"
echo "Expose HTTPS (tailscale funnel / cloudflared), then point TV → /api/tv-webhook"
echo "Keep BITGET_EXECUTE=dry_run until a test ENTRY_READY looks right."
