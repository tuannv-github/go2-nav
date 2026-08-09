#!/usr/bin/env bash
# Install/uninstall the systemd unit that applies Jetson max power at boot.
#
# Usage:
#   sudo ./install.sh              # install, enable, start
#   sudo ./install.sh uninstall    # disable and remove
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_SRC="${SCRIPT_DIR}/go2-cpu.service"
UNIT_NAME="go2-cpu.service"
UNIT_DST="/etc/systemd/system/${UNIT_NAME}"
RUN_SCRIPT="${SCRIPT_DIR}/cpu.sh"

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

sed \
  -e "s|^ExecStart=.*cpu\\.sh|ExecStart=${RUN_SCRIPT}|g" \
  "$UNIT_SRC" >"$UNIT_DST"
chmod 644 "$UNIT_DST"

systemctl daemon-reload
systemctl enable "$UNIT_NAME"
systemctl restart "$UNIT_NAME" || systemctl start "$UNIT_NAME" || true

echo "Installed $UNIT_DST (enabled at boot)"
echo "  status:  systemctl status $UNIT_NAME"
echo "  logs:    journalctl -u $UNIT_NAME -f"
echo "  manual:  $RUN_SCRIPT"
echo "  query:   $RUN_SCRIPT status"
