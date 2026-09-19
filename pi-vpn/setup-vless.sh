#!/usr/bin/env bash
# Xray VLESS + Reality on Ubuntu Pi (Shadowrocket backup when WireGuard UDP is blocked).
#
# Prereqs: DuckDNS hostname pointing at home IP; Deco port-forward TCP 443 → Pi.
#
#   sudo ./setup-vless.sh
#   # or with overrides:
#   sudo DUCKDNS_DOMAIN=max-trading VLESS_PORT=443 ./setup-vless.sh
#
# Imports secrets from ./secrets.env if present (DUCKDNS_DOMAIN, etc.).
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo $0"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ -f "${SCRIPT_DIR}/secrets.env" ]]; then
  # shellcheck disable=SC1091
  set -a
  source "${SCRIPT_DIR}/secrets.env"
  set +a
fi

DUCKDNS_DOMAIN="${DUCKDNS_DOMAIN:-max-trading}"
DUCKDNS_DOMAIN="${DUCKDNS_DOMAIN%.duckdns.org}"
FQDN="${DUCKDNS_DOMAIN}.duckdns.org"
VLESS_PORT="${VLESS_PORT:-443}"
REALITY_DEST="${REALITY_DEST:-www.microsoft.com:443}"
REALITY_SERVER_NAMES="${REALITY_SERVER_NAMES:-www.microsoft.com,microsoft.com}"
XRAY_DIR="/usr/local/etc/xray"
XRAY_BIN_DIR="/usr/local/bin"
CLIENT_OUT="/usr/local/etc/xray/vless-client.txt"
SHARE_LINK_OUT="/usr/local/etc/xray/vless-shadowrocket.txt"

echo "==> VLESS+Reality for ${FQDN}:${VLESS_PORT}"

arch="$(uname -m)"
case "${arch}" in
  aarch64|arm64) XRAY_ASSET="Xray-linux-arm64-v8a.zip" ;;
  x86_64|amd64)  XRAY_ASSET="Xray-linux-64.zip" ;;
  armv7l)        XRAY_ASSET="Xray-linux-arm32-v7a.zip" ;;
  *) echo "Unsupported arch: ${arch}"; exit 1 ;;
esac

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq curl unzip jq openssl ca-certificates

TMP="$(mktemp -d)"
cleanup() { rm -rf "${TMP}"; }
trap cleanup EXIT

echo "==> Downloading Xray (${XRAY_ASSET})"
# Pin to a recent release tag; fall back to latest if needed
XRAY_VER="$(curl -fsSL https://api.github.com/repos/XTLS/Xray-core/releases/latest | jq -r .tag_name)"
curl -fsSL -o "${TMP}/xray.zip" \
  "https://github.com/XTLS/Xray-core/releases/download/${XRAY_VER}/${XRAY_ASSET}"
unzip -qo "${TMP}/xray.zip" -d "${TMP}/xray"
install -m 755 "${TMP}/xray/xray" "${XRAY_BIN_DIR}/xray"
mkdir -p "${XRAY_DIR}"

if [[ ! -f "${XRAY_DIR}/uuid" ]]; then
  "${XRAY_BIN_DIR}/xray" uuid >"${XRAY_DIR}/uuid"
fi
UUID="$(tr -d '\r\n' <"${XRAY_DIR}/uuid")"

if [[ ! -f "${XRAY_DIR}/reality.json" ]]; then
  echo "==> Generating Reality keypair"
  RAW="$("${XRAY_BIN_DIR}/xray" x25519)"
  printf '%s\n' "${RAW}" >"${XRAY_DIR}/reality_raw.txt"
  PRIV="$(printf '%s\n' "${RAW}" | awk -F': *' 'BEGIN{IGNORECASE=1} /Private/ {print $2; exit}' | tr -d '\r[:space:]')"
  PUB="$(printf '%s\n' "${RAW}" | awk -F': *' 'BEGIN{IGNORECASE=1} /Password|Public/ {print $2; exit}' | tr -d '\r[:space:]')"
  if [[ -z "${PRIV}" || -z "${PUB}" ]]; then
    echo "Failed to parse xray x25519 output:"
    printf '%s\n' "${RAW}"
    exit 1
  fi
  SHORT_ID="$(openssl rand -hex 4)"
  jq -n --arg priv "${PRIV}" --arg pub "${PUB}" --arg sid "${SHORT_ID}" \
    '{privateKey:$priv, publicKey:$pub, shortId:$sid}' >"${XRAY_DIR}/reality.json"
  chmod 600 "${XRAY_DIR}/reality.json" "${XRAY_DIR}/reality_raw.txt"
fi

PRIV="$(jq -r .privateKey "${XRAY_DIR}/reality.json")"
PUB="$(jq -r .publicKey "${XRAY_DIR}/reality.json")"
SHORT_ID="$(jq -r .shortId "${XRAY_DIR}/reality.json")"

# Build serverNames JSON array
NAMES_JSON="$(echo "${REALITY_SERVER_NAMES}" | awk -F',' '{
  printf "["
  for (i=1;i<=NF;i++) {
    gsub(/^ +| +$/,"",$i)
    printf "%s\"%s\"", (i>1?",":""), $i
  }
  printf "]"
}')"

echo "==> Writing ${XRAY_DIR}/config.json"
cat >"${XRAY_DIR}/config.json" <<EOF
{
  "log": { "loglevel": "warning" },
  "inbounds": [
    {
      "listen": "0.0.0.0",
      "port": ${VLESS_PORT},
      "protocol": "vless",
      "settings": {
        "clients": [
          {
            "id": "${UUID}",
            "flow": "xtls-rprx-vision"
          }
        ],
        "decryption": "none"
      },
      "streamSettings": {
        "network": "tcp",
        "security": "reality",
        "realitySettings": {
          "show": false,
          "dest": "${REALITY_DEST}",
          "xver": 0,
          "serverNames": ${NAMES_JSON},
          "privateKey": "${PRIV}",
          "shortIds": ["${SHORT_ID}"]
        }
      },
      "sniffing": {
        "enabled": true,
        "destOverride": ["http", "tls", "quic"]
      }
    }
  ],
  "outbounds": [
    { "protocol": "freedom", "tag": "direct" },
    { "protocol": "blackhole", "tag": "block" }
  ]
}
EOF
chmod 600 "${XRAY_DIR}/config.json"

cat >/etc/systemd/system/xray.service <<EOF
[Unit]
Description=Xray VLESS Reality
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=${XRAY_BIN_DIR}/xray run -config ${XRAY_DIR}/config.json
Restart=on-failure
RestartSec=3
LimitNOFILE=1048576
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable xray
systemctl restart xray
sleep 1
systemctl --no-pager --full status xray || true

# Shadowrocket / v2rayN share link
# vless://uuid@host:port?encryption=none&flow=xtls-rprx-vision&security=reality&sni=...&fp=chrome&pbk=...&sid=...&type=tcp#name
SNI="$(echo "${REALITY_SERVER_NAMES}" | cut -d',' -f1 | tr -d ' ')"
SHARE="vless://${UUID}@${FQDN}:${VLESS_PORT}?encryption=none&flow=xtls-rprx-vision&security=reality&sni=${SNI}&fp=chrome&pbk=${PUB}&sid=${SHORT_ID}&type=tcp#${DUCKDNS_DOMAIN}-vless"

umask 077
cat >"${SHARE_LINK_OUT}" <<EOF
${SHARE}
EOF
cat >"${CLIENT_OUT}" <<EOF
Protocol: VLESS + Reality (TCP ${VLESS_PORT})
Address:  ${FQDN}
Port:     ${VLESS_PORT}
UUID:     ${UUID}
Flow:     xtls-rprx-vision
Security: reality
SNI:      ${SNI}
Fingerprint: chrome
Public key: ${PUB}
Short ID: ${SHORT_ID}

Shadowrocket: + → Scan/Type → import link below (or Type: VLESS and fill fields)

${SHARE}
EOF
chmod 600 "${CLIENT_OUT}" "${SHARE_LINK_OUT}"

if command -v ufw >/dev/null 2>&1; then
  ufw allow "${VLESS_PORT}/tcp" comment 'Xray VLESS' || true
fi

cat <<EOF

============================================
 VLESS + Reality is running
============================================
 Deco: port-forward TCP ${VLESS_PORT} → Pi LAN IP

 Client details:
   sudo cat ${CLIENT_OUT}

 Share link (import in Shadowrocket):
   sudo cat ${SHARE_LINK_OUT}

 Keep WireGuard as profile A; use this as profile B in China.

 LEDGER journal: still use VPN tunnel → http://10.8.0.1:3000
 (do not put the journal on public :443 — this port is for VLESS)
EOF
