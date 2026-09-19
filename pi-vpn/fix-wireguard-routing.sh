#!/usr/bin/env bash
# Fix WireGuard: correct NAT interface + optional split-tunnel client (keeps normal internet).
#
#   sudo ./fix-wireguard-routing.sh
#
# Afterward re-import /etc/wireguard/clients/iphone.conf into Shadowrocket.
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run: sudo $0"
  exit 1
fi

WG_CONF=/etc/wireguard/wg0.conf
CLIENT_CONF=/etc/wireguard/clients/iphone.conf

if [[ ! -f "${WG_CONF}" ]]; then
  echo "Missing ${WG_CONF}"
  exit 1
fi

WAN_IF="$(ip -4 route show default | awk '{print $5; exit}')"
if [[ -z "${WAN_IF}" ]]; then
  echo "No default route — connect Ethernet/Wi-Fi first."
  exit 1
fi
echo "==> WAN interface for NAT: ${WAN_IF}"

# Ensure forwarding
install -d -m 0755 /etc/sysctl.d
echo 'net.ipv4.ip_forward=1' >/etc/sysctl.d/99-wireguard-forward.conf
sysctl -p /etc/sysctl.d/99-wireguard-forward.conf >/dev/null

# Rewrite PostUp/PostDown to current WAN iface (fixes wlan0 vs eth0 mismatch)
if grep -q 'PostUp' "${WG_CONF}"; then
  sed -i -E "s|-o [a-zA-Z0-9]+ -j MASQUERADE|-o ${WAN_IF} -j MASQUERADE|g" "${WG_CONF}"
else
  # Insert after ListenPort / PrivateKey block roughly after Address line
  awk -v ifc="${WAN_IF}" '
    BEGIN{done=0}
    /^\[Interface\]/{print; in_if=1; print; next}
    in_if && /^\[Peer\]/ && !done {
      print "PostUp = iptables -A FORWARD -i wg0 -j ACCEPT; iptables -A FORWARD -o wg0 -j ACCEPT; iptables -t nat -A POSTROUTING -o " ifc " -j MASQUERADE"
      print "PostDown = iptables -D FORWARD -i wg0 -j ACCEPT; iptables -D FORWARD -o wg0 -j ACCEPT; iptables -t nat -D POSTROUTING -o " ifc " -j MASQUERADE"
      done=1
      in_if=0
    }
    {print}
  ' "${WG_CONF}" >"${WG_CONF}.tmp" && mv "${WG_CONF}.tmp" "${WG_CONF}"
fi
chmod 600 "${WG_CONF}"

echo "==> Updated ${WG_CONF} NAT → ${WAN_IF}"
grep -E 'PostUp|PostDown|Address|ListenPort' "${WG_CONF}" || true

# Split tunnel client: home VPN + LAN only — phone internet stays on cellular/Wi-Fi
# Change SPLIT=0 to keep full tunnel (all traffic via Pi)
SPLIT="${SPLIT:-1}"
if [[ -f "${CLIENT_CONF}" && "${SPLIT}" == "1" ]]; then
  echo "==> Setting split-tunnel AllowedIPs on ${CLIENT_CONF}"
  # Common home LANs + WireGuard subnet
  sed -i 's|^AllowedIPs = .*|AllowedIPs = 10.8.0.0/24, 192.168.0.0/16, 10.0.0.0/8|' "${CLIENT_CONF}"
  chmod 600 "${CLIENT_CONF}"
  echo "    AllowedIPs = 10.8.0.0/24, 192.168.0.0/16, 10.0.0.0/8"
fi

systemctl daemon-reload
systemctl restart wg-quick@wg0
sleep 1
wg show

echo
echo "Re-import into Shadowrocket:"
echo "  sudo cat ${CLIENT_CONF}"
echo "  sudo qrencode -t ansiutf8 < ${CLIENT_CONF}"
echo
echo "Then on phone (VPN on):"
echo "  http://10.8.0.1:3000"
echo "  or http://PI_LAN_IP:3000"
echo
echo "At home Wi-Fi without VPN, keep using http://192.168.x.x:3000"
