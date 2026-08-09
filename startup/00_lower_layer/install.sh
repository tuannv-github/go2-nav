#!/usr/bin/env bash
# Install/uninstall the systemd unit that stops Go2 lower-layer mapping on boot.
#
# Usage:
#   sudo ./install.sh              # install, enable, start
#   sudo ./install.sh uninstall    # disable and remove
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_SRC="${SCRIPT_DIR}/go2-lower-layer.service"
UNIT_NAME="go2-lower-layer.service"
UNIT_DST="/etc/systemd/system/${UNIT_NAME}"
SERVICE_SCRIPT="${SCRIPT_DIR}/service_on_off.sh"
RUN_USER="${SUDO_USER:-${USER:-unitree}}"

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
if [[ ! -x "$SERVICE_SCRIPT" ]]; then
  chmod +x "$SERVICE_SCRIPT"
fi

sed \
  -e "s|^ExecStart=.*service_on_off\\.sh|ExecStart=${SERVICE_SCRIPT}|g" \
  -e "s|WorkingDirectory=/home/unitree/go2-nav|WorkingDirectory=$(cd "${SCRIPT_DIR}/../.." && pwd)|g" \
  -e "s|User=unitree|User=${RUN_USER}|g" \
  -e "s|Group=unitree|Group=${RUN_USER}|g" \
  -e "s|Environment=HOME=/home/unitree|Environment=HOME=$(getent passwd "${RUN_USER}" | cut -d: -f6)|g" \
  -e "s|Environment=CYCLONEDDS_URI=file:///home/unitree/go2-nav/cyclonedds/cyclonedds.eth0.xml|Environment=CYCLONEDDS_URI=file://$(cd "${SCRIPT_DIR}/../.." && pwd)/cyclonedds/cyclonedds.eth0.xml|g" \
  "$UNIT_SRC" >"$UNIT_DST"
chmod 644 "$UNIT_DST"

systemctl daemon-reload
systemctl enable "$UNIT_NAME"
# Do not block install on the oneshot (it talks to the dog over DDS).
systemctl start --no-block "$UNIT_NAME" || true

echo "Installed $UNIT_DST (enabled at boot)"
echo "  status:  systemctl status $UNIT_NAME"
echo "  logs:    journalctl -u $UNIT_NAME -f"
echo "  manual:  $SERVICE_SCRIPT off|on|status|list"
