#!/usr/bin/env bash
# DuckDNS updater for Ubuntu Raspberry Pi + optional WireGuard Endpoint rewrite.
#
# 1) Create a free name at https://www.duckdns.org (sign in with GitHub/Google)
# 2) Copy your token and subdomain (e.g. myhome → myhome.duckdns.org)
# 3) On the Pi:
#      sudo DUCKDNS_DOMAIN=myhome DUCKDNS_TOKEN=xxxxxxxx ./setup-duckdns.sh
#
# Optional:
#   UPDATE_WIREGUARD=1   rewrite Endpoint in /etc/wireguard/clients/*.conf
#   VPN_PORT=51820
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo DUCKDNS_DOMAIN=... DUCKDNS_TOKEN=... $0"
  exit 1
fi

DUCKDNS_DOMAIN="${DUCKDNS_DOMAIN:-}"
DUCKDNS_TOKEN="${DUCKDNS_TOKEN:-}"
UPDATE_WIREGUARD="${UPDATE_WIREGUARD:-1}"
VPN_PORT="${VPN_PORT:-51820}"
INSTALL_DIR="/opt/duckdns"
LOG_FILE="/var/log/duckdns.log"

if [[ -z "${DUCKDNS_DOMAIN}" || -z "${DUCKDNS_TOKEN}" ]]; then
  cat <<'EOF'
Missing DUCKDNS_DOMAIN and/or DUCKDNS_TOKEN.

1. Open https://www.duckdns.org and sign in
2. Create a subdomain (example: tradingpi)
3. Copy the token shown on the page
4. Re-run:

   sudo DUCKDNS_DOMAIN=tradingpi DUCKDNS_TOKEN=your-token-here \
     ./setup-duckdns.sh

Optional: UPDATE_WIREGUARD=0 to skip rewriting WireGuard client configs.
EOF
  exit 1
fi

# Strip accidental .duckdns.org suffix
DUCKDNS_DOMAIN="${DUCKDNS_DOMAIN%.duckdns.org}"
FQDN="${DUCKDNS_DOMAIN}.duckdns.org"

echo "==> Installing DuckDNS updater for ${FQDN}"
mkdir -p "${INSTALL_DIR}"
chmod 700 "${INSTALL_DIR}"

# Persist credentials for cron
cat >"${INSTALL_DIR}/config" <<EOF
DUCKDNS_DOMAIN=${DUCKDNS_DOMAIN}
DUCKDNS_TOKEN=${DUCKDNS_TOKEN}
EOF
chmod 600 "${INSTALL_DIR}/config"

cat >"${INSTALL_DIR}/update.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
# shellcheck disable=SC1091
source /opt/duckdns/config
echo url="https://www.duckdns.org/update?domains=${DUCKDNS_DOMAIN}&token=${DUCKDNS_TOKEN}&ip=" \
  | curl -k -o /opt/duckdns/duck.log -K -
date >> /var/log/duckdns.log
cat /opt/duckdns/duck.log >> /var/log/duckdns.log
echo >> /var/log/duckdns.log
EOF
chmod 700 "${INSTALL_DIR}/update.sh"

touch "${LOG_FILE}"
chmod 644 "${LOG_FILE}"

echo "==> Running first update"
"${INSTALL_DIR}/update.sh"
RESULT="$(tr -d '\r\n' <"${INSTALL_DIR}/duck.log" || true)"
echo "    DuckDNS response: ${RESULT}"
if [[ "${RESULT}" != "OK" ]]; then
  echo "DuckDNS did not return OK. Check domain/token and try again."
  exit 1
fi

# Cron every 5 minutes
CRON_LINE="*/5 * * * * root /opt/duckdns/update.sh >/dev/null 2>&1"
echo "${CRON_LINE}" >/etc/cron.d/duckdns
chmod 644 /etc/cron.d/duckdns

RESOLVED="$(getent ahostsv4 "${FQDN}" | awk '{print $1; exit}' || true)"
PUBLIC_NOW="$(curl -4 -fsS --max-time 8 https://ifconfig.me || true)"
echo "==> ${FQDN} resolves to: ${RESOLVED:-unknown}"
echo "==> Current public IP:   ${PUBLIC_NOW:-unknown}"

if [[ "${UPDATE_WIREGUARD}" == "1" ]]; then
  CLIENT_DIR="/etc/wireguard/clients"
  if [[ -d "${CLIENT_DIR}" ]]; then
    echo "==> Updating WireGuard client Endpoint → ${FQDN}:${VPN_PORT}"
    shopt -s nullglob
    for conf in "${CLIENT_DIR}"/*.conf; do
      if grep -q '^Endpoint' "${conf}"; then
        sed -i "s|^Endpoint = .*|Endpoint = ${FQDN}:${VPN_PORT}|" "${conf}"
      else
        # Insert under [Peer] if missing
        awk -v ep="Endpoint = ${FQDN}:${VPN_PORT}" '
          /^\[Peer\]/ { print; print ep; next }
          /^Endpoint/ { next }
          { print }
        ' "${conf}" >"${conf}.tmp" && mv "${conf}.tmp" "${conf}"
      fi
      chmod 600 "${conf}"
      echo "    updated $(basename "${conf}")"
    done
    echo
    echo "Re-import the client config into Shadowrocket (or edit Endpoint manually):"
    echo "  sudo cat /etc/wireguard/clients/iphone.conf"
  else
    echo "==> No ${CLIENT_DIR} yet — skip WireGuard rewrite (run WireGuard setup first)."
  fi
fi

cat <<EOF

============================================
 DuckDNS ready: ${FQDN}
============================================
 Updater:  /opt/duckdns/update.sh
 Cron:     every 5 minutes (/etc/cron.d/duckdns)
 Log:      ${LOG_FILE}

 Shadowrocket WireGuard Endpoint should be:
   ${FQDN}:${VPN_PORT}

 Test:
   dig +short ${FQDN}
   curl -4 ifconfig.me

 Next (optional China-resilient backup): Trojan/VLESS on TCP 443.
EOF
