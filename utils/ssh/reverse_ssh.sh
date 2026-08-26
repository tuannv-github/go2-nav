#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

SSH_PORT="${SERVER_SSH_PORT:-22}"

while true; do
    echo "Starting reverse SSH tunnel... at $(date)"

    # Use SSH key for authentication
    SSH_KEY="$HOME/.ssh/id_rsa_unitree_robot"

    echo "SSH key: $SSH_KEY"
    echo "Server user name: $SERVER_USER_NAME"
    echo "Server IP address: $SERVER_IP_ADDRESS"
    echo "Server SSH port: $SSH_PORT"
    echo "Forwarded reverse port: $SERVER_PORT"
    echo "--------------------------------"

    ssh -i "$SSH_KEY" \
        -p "$SSH_PORT" \
        -o ConnectTimeout=10 \
        -o ServerAliveInterval=5 \
        -o ServerAliveCountMax=3 \
        -o TCPKeepAlive=yes \
        -o ExitOnForwardFailure=yes \
        -o StrictHostKeyChecking=accept-new \
        -N \
        -R "*:${SERVER_PORT}:localhost:22" \
        "${SERVER_USER_NAME}@${SERVER_IP_ADDRESS}"

    echo "SSH disconnected. Reconnecting in 3 seconds..."
    sleep 3
done

