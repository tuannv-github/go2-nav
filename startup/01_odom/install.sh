#!/usr/bin/env bash
# Install/uninstall the systemd unit that publishes /odom from /utlidar/robot_odom.
#
# Usage:
#   sudo ./install.sh              # install, enable, start
#   sudo ./install.sh uninstall    # disable and remove
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_SRC="${SCRIPT_DIR}/go2-odom.service"
UNIT_NAME="go2-odom.service"
UNIT_DST="/etc/systemd/system/${UNIT_NAME}"
RUN_SCRIPT="${SCRIPT_DIR}/run_odom.sh"
RUN_USER="${SUDO_USER:-${USER:-unitree}}"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

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
  -e "s|/home/unitree/go2-nav/startup/01_odom/run_odom.sh|${RUN_SCRIPT}|g" \
  -e "s|WorkingDirectory=/home/unitree/go2-nav|WorkingDirectory=${PROJECT_DIR}|g" \
  -e "s|User=unitree|User=${RUN_USER}|g" \
  -e "s|Group=unitree|Group=${RUN_USER}|g" \
  -e "s|Environment=HOME=/home/unitree|Environment=HOME=${RUN_HOME}|g" \
  "$UNIT_SRC" >"$UNIT_DST"
chmod 644 "$UNIT_DST"

systemctl daemon-reload
systemctl enable "$UNIT_NAME"
systemctl restart "$UNIT_NAME" || systemctl start "$UNIT_NAME" || true

echo "Installed $UNIT_DST (enabled at boot)"
echo "  status:  systemctl status $UNIT_NAME"
echo "  logs:    journalctl -u $UNIT_NAME -f"
echo "  manual:  $RUN_SCRIPT"
echo "  echo:    ${SCRIPT_DIR}/echo_odom.sh --field pose.pose"
echo "  ext:     ${SCRIPT_DIR}/echo_odom_ext.sh  |  other PC: Peer robot IP (readme.md)"
