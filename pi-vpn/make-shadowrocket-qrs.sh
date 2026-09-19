#!/usr/bin/env bash
# Show / save Shadowrocket QR codes for WireGuard + VLESS (run on the Pi).
#
#   sudo ./make-shadowrocket-qrs.sh
#
# Scan the terminal QR with Shadowrocket, or open the PNGs on a screen and scan.
set -euo pipefail

WG_CONF="${WG_CONF:-/etc/wireguard/clients/iphone.conf}"
VLESS_LINK="${VLESS_LINK:-/usr/local/etc/xray/vless-shadowrocket.txt}"
OUT_DIR="${OUT_DIR:-/home/${SUDO_USER:-$USER}/hello-world/pi-vpn/qrcodes}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run: sudo $0"
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get install -y -qq qrencode >/dev/null

mkdir -p "${OUT_DIR}"
chmod 700 "${OUT_DIR}"

if [[ ! -f "${WG_CONF}" ]]; then
  echo "Missing ${WG_CONF} — run setup-wireguard.sh / setup-duckdns.sh first."
  exit 1
fi
if [[ ! -f "${VLESS_LINK}" ]]; then
  echo "Missing ${VLESS_LINK} — run setup-vless.sh first."
  exit 1
fi

WG_PNG="${OUT_DIR}/shadowrocket-wireguard.png"
VLESS_PNG="${OUT_DIR}/shadowrocket-vless.png"

qrencode -o "${WG_PNG}" -s 8 -m 2 <"${WG_CONF}"
qrencode -o "${VLESS_PNG}" -s 8 -m 2 <"${VLESS_LINK}"
chown -R "${SUDO_USER:-$USER}:${SUDO_USER:-$USER}" "${OUT_DIR}" 2>/dev/null || true

echo
echo "############################################"
echo "#  PROFILE A — WireGuard (scan this)      #"
echo "############################################"
qrencode -t ansiutf8 <"${WG_CONF}"
echo
echo "Saved: ${WG_PNG}"
echo
echo "############################################"
echo "#  PROFILE B — VLESS (scan this)          #"
echo "############################################"
qrencode -t ansiutf8 <"${VLESS_LINK}"
echo
echo "Saved: ${VLESS_PNG}"
echo
echo "Shadowrocket → + → Scan QR Code (once per profile)."
echo "Or open the PNGs:  xdg-open ${OUT_DIR}   (on Pi desktop)"
echo
echo "Link text (VLESS) also at: ${VLESS_LINK}"
