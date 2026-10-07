#!/bin/bash
# Stop and remove the Unitree Go2 Wi-Fi Mesh Auto-Roaming systemd service.
# Location: /home/unitree/go2-nav/wifi/uninstall.sh

set -e

SERVICE_NAME="go2-wifi-mesh.service"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}"
SOCKET_PATH="/tmp/go2_wifi_mesh.sock"

echo -e "\033[1;36m=================================================================\033[0m"
echo -e "\033[1;36m Stopping and removing Unitree Go2 Wi-Fi Mesh Auto-Roaming\033[0m"
echo -e "\033[1;36m=================================================================\033[0m"

sudo systemctl stop "${SERVICE_NAME}" 2>/dev/null || true
sudo systemctl disable "${SERVICE_NAME}" 2>/dev/null || true

if [[ -f "${SERVICE_PATH}" ]]; then
    sudo rm -f "${SERVICE_PATH}"
    echo -e "\033[92m[✓] Removed ${SERVICE_PATH}\033[0m"
else
    echo -e "\033[33m[!] ${SERVICE_PATH} was not installed\033[0m"
fi

sudo systemctl daemon-reload
sudo systemctl reset-failed "${SERVICE_NAME}" 2>/dev/null || true

if [[ -S "${SOCKET_PATH}" ]]; then
    sudo rm -f "${SOCKET_PATH}"
    echo -e "\033[92m[✓] Removed ${SOCKET_PATH}\033[0m"
fi

echo -e "\033[92m[✓] ${SERVICE_NAME} is stopped and uninstalled\033[0m"
echo -e "\033[36m-----------------------------------------------------------------\033[0m"
systemctl status "${SERVICE_NAME}" --no-pager 2>&1 | head -n 5 || true
echo -e "\033[1;36m=================================================================\033[0m"
