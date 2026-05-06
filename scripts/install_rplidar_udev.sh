#!/usr/bin/env bash
# Install udev rules for RPLidar USB serial into /etc and reload udev.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RULES_SRC="${REPO_ROOT}/udev/rplidar.rules"
DEST="/etc/udev/rules.d/99-go2-nav-rplidar.rules"

if [[ ! -f "${RULES_SRC}" ]]; then
  echo "Missing rules file: ${RULES_SRC}" >&2
  exit 1
fi

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Installing udev rules requires sudo."
  exec sudo bash "${BASH_SOURCE[0]}"
fi

cp -f "${RULES_SRC}" "${DEST}"
chmod 644 "${DEST}"

udevadm control --reload-rules
udevadm trigger --subsystem-match=tty

echo "Installed ${DEST}"
echo "Unplug and replug the lidar USB cable (or reboot), then check:"
echo "  ls -l /dev/rplidar /dev/ttyUSB*"
echo "Identify your adapter with: udevadm info --query=all --name=/dev/ttyUSB0 | grep -E idVendor|idProduct"
