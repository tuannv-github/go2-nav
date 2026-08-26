#!/bin/bash

source common.sh

# Check if key already exists
if [ -f ~/.ssh/id_rsa_unitree_robot ]; then
    echo "SSH key already exists. Regenerating..."
    rm -f ~/.ssh/id_rsa_unitree_robot ~/.ssh/id_rsa_unitree_robot.pub
fi

# Generate SSH key pair (non-interactive)
ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa_unitree_robot -q

# Check if public key was created successfully
if [ ! -f ~/.ssh/id_rsa_unitree_robot.pub ]; then
    echo "Error: Failed to generate SSH key pair"
    exit 1
fi

# Create ~/.ssh directory on remote server if it doesn't exist
echo "Creating ~/.ssh directory on remote server..."
ssh -p 2200 $SERVER_USER_NAME@$SERVER_IP_ADDRESS "mkdir -p ~/.ssh && chmod 700 ~/.ssh"

# Copy public key to server
# Use $HOME instead of ~ to ensure proper expansion
PUB_KEY_PATH="$HOME/.ssh/id_rsa_unitree_robot.pub"

# Use ssh-copy-id to copy and add the public key to authorized_keys
# -i specifies the identity file, -p specifies the port
SSH_KEY="$HOME/.ssh/id_rsa_unitree_robot"
echo "Copying SSH public key to server using ssh-copy-id..."
CMD="ssh-copy-id -i $SSH_KEY -p 2200 $SERVER_USER_NAME@$SERVER_IP_ADDRESS"
echo $CMD

$CMD
if [ $? -eq 0 ]; then
    echo "Successfully copied SSH public key to server"
else
    echo "Error: Failed to copy SSH public key to server"
    exit 1
fi
