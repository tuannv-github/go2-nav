#!/bin/bash

source common.sh

# Generate SSH key if it doesn't exist
ssh-keygen -t ed25519

# Copy SSH key to server
ssh-copy-id $SERVER_USER_NAME@$SERVER_IP_ADDRESS

# Enable GatewayPorts on the server's sshd_config
echo "Updating GatewayPorts in sshd_config on server..."
echo "Note: You may be prompted for sudo password on the server"

ssh -t $SERVER_USER_NAME@$SERVER_IP_ADDRESS "sudo sed -i '/^#\?GatewayPorts/c\GatewayPorts yes' /etc/ssh/sshd_config && sudo systemctl restart sshd"

echo "GatewayPorts has been set to yes and sshd restarted on the server."
