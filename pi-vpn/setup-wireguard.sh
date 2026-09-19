#!/usr/bin/env bash
# WireGuard VPN server setup for Ubuntu on Raspberry Pi
# Client: iPhone Shadowrocket (WireGuard profile) or WireGuard app
#
# Usage (on the Pi):
#   curl -fsSL ... | bash
#   OR:
#   chmod +x setup-wireguard.sh && sudo ./setup-wireguard.sh
#
# Optional env overrides:
#   VPN_PORT=51820
#   VPN_SUBNET=10.8.0.0/24
#   VPN_SERVER_IP=10.8.0.1
#   CLIENT_NAME=iphone
#   SERVER_PUBLIC_IP=   # if unset, script tries to detect

set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo $0"
  exit 1
fi

VPN_PORT="${VPN_PORT:-51820}"
VPN_SUBNET="${VPN_SUBNET:-10.8.0.0/24}"
VPN_SERVER_IP="${VPN_SERVER_IP:-10.8.0.1}"
CLIENT_NAME="${CLIENT_NAME:-iphone}"
WG_DIR="/etc/wireguard"
CLIENT_DIR="${WG_DIR}/clients"
CONF="${WG_DIR}/wg0.conf"

echo "==> Installing packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq wireguard wireguard-tools qrencode iptables

# Detect main outbound interface (usually eth0 or wlan0)
WAN_IF="$(ip -4 route show default | awk '{print $5; exit}')"
if [[ -z "${WAN_IF}" ]]; then
  echo "Could not detect default network interface. Connect Ethernet/Wi-Fi first."
  exit 1
fi
echo "==> WAN interface: ${WAN_IF}"

# Public IP for client endpoint (override with SERVER_PUBLIC_IP=x.x.x.x)
if [[ -z "${SERVER_PUBLIC_IP:-}" ]]; then
  SERVER_PUBLIC_IP="$(curl -4 -fsS --max-time 8 https://ifconfig.me || true)"
fi
if [[ -z "${SERVER_PUBLIC_IP}" ]]; then
  SERVER_PUBLIC_IP="$(curl -4 -fsS --max-time 8 https://api.ipify.org || true)"
fi
if [[ -z "${SERVER_PUBLIC_IP}" ]]; then
  echo "Could not detect public IP. Re-run with: SERVER_PUBLIC_IP=YOUR.IP.HERE sudo -E $0"
  exit 1
fi
echo "==> Public endpoint: ${SERVER_PUBLIC_IP}:${VPN_PORT}"

echo "==> Enabling IPv4 forwarding"
install -d -m 0755 /etc/sysctl.d
cat >/etc/sysctl.d/99-wireguard-forward.conf <<'EOF'
net.ipv4.ip_forward=1
EOF
sysctl -p /etc/sysctl.d/99-wireguard-forward.conf >/dev/null

umask 077
mkdir -p "${WG_DIR}" "${CLIENT_DIR}"

if [[ ! -f "${WG_DIR}/server_private.key" ]]; then
  echo "==> Generating server keys"
  wg genkey | tee "${WG_DIR}/server_private.key" | wg pubkey >"${WG_DIR}/server_public.key"
fi
SERVER_PRIV="$(cat "${WG_DIR}/server_private.key")"
SERVER_PUB="$(cat "${WG_DIR}/server_public.key")"

CLIENT_PRIV_FILE="${CLIENT_DIR}/${CLIENT_NAME}_private.key"
CLIENT_PUB_FILE="${CLIENT_DIR}/${CLIENT_NAME}_public.key"
CLIENT_CONF_FILE="${CLIENT_DIR}/${CLIENT_NAME}.conf"

if [[ ! -f "${CLIENT_PRIV_FILE}" ]]; then
  echo "==> Generating client keys (${CLIENT_NAME})"
  wg genkey | tee "${CLIENT_PRIV_FILE}" | wg pubkey >"${CLIENT_PUB_FILE}"
fi
CLIENT_PRIV="$(cat "${CLIENT_PRIV_FILE}")"
CLIENT_PUB="$(cat "${CLIENT_PUB_FILE}")"
CLIENT_IP="10.8.0.2"

echo "==> Writing ${CONF}"
cat >"${CONF}" <<EOF
[Interface]
Address = ${VPN_SERVER_IP}/24
ListenPort = ${VPN_PORT}
PrivateKey = ${SERVER_PRIV}
# NAT traffic from VPN clients out to the internet / LAN
PostUp = iptables -A FORWARD -i wg0 -j ACCEPT; iptables -A FORWARD -o wg0 -j ACCEPT; iptables -t nat -A POSTROUTING -o ${WAN_IF} -j MASQUERADE
PostDown = iptables -D FORWARD -i wg0 -j ACCEPT; iptables -D FORWARD -o wg0 -j ACCEPT; iptables -t nat -D POSTROUTING -o ${WAN_IF} -j MASQUERADE

[Peer]
# ${CLIENT_NAME}
PublicKey = ${CLIENT_PUB}
AllowedIPs = ${CLIENT_IP}/32
EOF
chmod 600 "${CONF}"

echo "==> Writing client config ${CLIENT_CONF_FILE}"
# AllowedIPs = 0.0.0.0/0 sends ALL phone traffic through Pi (full tunnel).
# For home-LAN-only access, use: AllowedIPs = 10.8.0.0/24, 192.168.0.0/16
cat >"${CLIENT_CONF_FILE}" <<EOF
[Interface]
PrivateKey = ${CLIENT_PRIV}
Address = ${CLIENT_IP}/24
DNS = 1.1.1.1

[Peer]
PublicKey = ${SERVER_PUB}
Endpoint = ${SERVER_PUBLIC_IP}:${VPN_PORT}
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
EOF
chmod 600 "${CLIENT_CONF_FILE}"

echo "==> Enabling wg0"
systemctl enable wg-quick@wg0
systemctl restart wg-quick@wg0
wg show || true

if command -v ufw >/dev/null 2>&1; then
  echo "==> Opening UDP ${VPN_PORT} in UFW (if active)"
  ufw allow "${VPN_PORT}/udp" comment 'WireGuard' || true
  ufw route allow in on wg0 out on "${WAN_IF}" || true
fi

echo
echo "============================================"
echo " WireGuard is up on UDP ${VPN_PORT}"
echo " Client config: ${CLIENT_CONF_FILE}"
echo "============================================"
echo
echo "ROUTER: port-forward UDP ${VPN_PORT} -> this Pi LAN IP"
echo "  Pi LAN IP: $(ip -4 -o addr show "${WAN_IF}" | awk '{print $4}' | cut -d/ -f1 | head -1)"
echo
echo "Shadowrocket / WireGuard on iPhone:"
echo "  1) Copy ${CLIENT_CONF_FILE} to your phone (AirDrop / scp / cat below)"
echo "  2) Shadowrocket -> Add -> Type: WireGuard -> import config"
echo "  3) Or scan QR (WireGuard iOS app also works):"
echo
qrencode -t ansiutf8 <"${CLIENT_CONF_FILE}" || true
echo
echo "----- client config begin -----"
cat "${CLIENT_CONF_FILE}"
echo "----- client config end -------"
echo
echo "Test from cellular data (not home Wi-Fi)."
echo "If connection fails: check router UDP forward, CGNAT, and public IP."
