#!/bin/bash
# Installation script for Unitree Go2 Wi-Fi Mesh Auto-Roaming Systemd Service
# Location: /home/unitree/go2-nav/wifi/install.sh

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="go2-wifi-mesh.service"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}"

echo -e "\033[1;36m=================================================================\033[0m"
echo -e "\033[1;36m 🚀 Installing Unitree Go2 Wi-Fi Mesh Auto-Roaming Systemd Service\033[0m"
echo -e "\033[1;36m=================================================================\033[0m"

# 1. Make scripts executable
chmod +x "${DIR}/wifi_mesh.sh"
chmod +x "${DIR}/wifi_mesh.py"
chmod +x "${DIR}/wifi_console.sh"
chmod +x "${DIR}/install.sh"

# 2. Write systemd unit file
cat <<EOF | sudo tee "${SERVICE_PATH}" > /dev/null
[Unit]
Description=Unitree Go2 Wi-Fi 5GHz Mesh Auto-Roaming Daemon
After=network-online.target NetworkManager.service
Wants=NetworkManager.service

[Service]
Type=simple
User=root
WorkingDirectory=${DIR}
ExecStart=/usr/bin/python3 ${DIR}/wifi_mesh.py --auto-roam --interval 1.0 --udp-port 9999 --socket-path /tmp/go2_wifi_mesh.sock
PrivateTmp=false
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

echo -e "\033[92m[✓] Created systemd service: ${SERVICE_PATH}\033[0m"

# 3. Reload systemd daemon & enable service
sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"
sudo systemctl restart "${SERVICE_NAME}"

echo -e "\033[92m[✓] Enabled & Started ${SERVICE_NAME}\033[0m"
echo -e "\033[36m-----------------------------------------------------------------\033[0m"
echo -e "\033[1mService Status:\033[0m"
sudo systemctl status "${SERVICE_NAME}" --no-pager | head -n 12

echo -e "\033[36m-----------------------------------------------------------------\033[0m"
echo -e "\033[1;33m📋 VERIFICATION & CONSOLE COMMANDS:\033[0m"
echo -e "  \033[1m1. Read Live Unix / UDP Console Stream:\033[0m"
echo -e "     ${DIR}/wifi_console.sh"
echo -e "  \033[1m2. Check Systemd Logs:\033[0m"
echo -e "     sudo journalctl -u ${SERVICE_NAME} -f"
echo -e "\033[1;36m=================================================================\033[0m"
