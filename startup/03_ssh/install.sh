#!/usr/bin/env bash
# Install/uninstall the systemd unit for the reverse SSH tunnel.
#
# Usage:
#   sudo ./install.sh              # install, enable, start
#   sudo ./install.sh uninstall    # disable and remove
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_SRC="${SCRIPT_DIR}/go2-ssh.service"
UNIT_NAME="go2-ssh.service"
UNIT_DST="/etc/systemd/system/${UNIT_NAME}"
RUN_SCRIPT="${SCRIPT_DIR}/run_tunnel.sh"
RUN_USER="${SUDO_USER:-${USER:-unitree}}"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
LISTEN_PORT="${SSH_TUNNEL_LISTEN_PORT:-4123}"

usage() {
  sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'
  exit 1
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" || "${1:-}" == "help" ]]; then
  usage
fi

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Installing systemd unit requires sudo."
  exec sudo bash "$0" "$@"
fi

cmd="${1:-install}"

case "$cmd" in
  uninstall|remove)
    systemctl disable --now "$UNIT_NAME" 2>/dev/null || true
    rm -f "$UNIT_DST"
    systemctl daemon-reload
    echo "Removed $UNIT_DST"
    exit 0
    ;;
  install|"")
    ;;
  *)
    echo "error: unknown command: $cmd" >&2
    usage
    ;;
esac

if [[ ! -f "$UNIT_SRC" ]]; then
  echo "error: missing unit template: $UNIT_SRC" >&2
  exit 1
fi
chmod +x "$RUN_SCRIPT"

RUN_HOME="$(getent passwd "${RUN_USER}" | cut -d: -f6)"
sed \
  -e "s|/home/unitree/go2-nav/startup/03_ssh/run_tunnel.sh|${RUN_SCRIPT}|g" \
  -e "s|WorkingDirectory=/home/unitree/go2-nav|WorkingDirectory=${PROJECT_DIR}|g" \
  -e "s|User=unitree|User=${RUN_USER}|g" \
  -e "s|Group=unitree|Group=${RUN_USER}|g" \
  -e "s|Environment=HOME=/home/unitree|Environment=HOME=${RUN_HOME}|g" \
  "$UNIT_SRC" >"$UNIT_DST"
chmod 644 "$UNIT_DST"

# Free remote listen port if a manual tunnel is still up.
pkill -f "[s]sh .* -R ${LISTEN_PORT}:localhost:22" 2>/dev/null || true
sleep 0.5

systemctl daemon-reload
systemctl enable "$UNIT_NAME"
systemctl restart "$UNIT_NAME" || systemctl start "$UNIT_NAME" || true

echo "Installed $UNIT_DST (enabled at boot)"
echo "  status:  systemctl status $UNIT_NAME"
echo "  logs:    journalctl -u $UNIT_NAME -f"
echo "  manual:  $RUN_SCRIPT"
echo "  query:   $RUN_SCRIPT status"
echo "  remote:  ssh -p ${LISTEN_PORT} ${RUN_USER}@127.0.0.1   # on host master"
