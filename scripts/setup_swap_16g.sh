#!/bin/bash
# Script to set up a 16GB swap file
# Run with: sudo ./setup_swap_16g.sh

set -e

SWAP_FILE="/swapfile"
SWAP_SIZE="16G"

echo "Setting up 16GB swap file..."

# Disable zram service to prevent it from re-enabling on reboot
echo "Disabling zram service..."
systemctl disable nvzramconfig.service 2>/dev/null || true
systemctl stop nvzramconfig.service 2>/dev/null || true

# Disable all current swap
echo "Disabling current swap devices..."
swapoff -a 2>/dev/null || true

# Remove old swap file if it exists
if [ -f "$SWAP_FILE" ]; then
    echo "Removing existing swap file..."
    swapoff "$SWAP_FILE" 2>/dev/null || true
    rm -f "$SWAP_FILE"
fi

# Create 16GB swap file
echo "Creating 16GB swap file at $SWAP_FILE..."
fallocate -l "$SWAP_SIZE" "$SWAP_FILE" || dd if=/dev/zero of="$SWAP_FILE" bs=1M count=16384

# Set secure permissions (only root can read/write)
chmod 600 "$SWAP_FILE"

# Format as swap
echo "Formatting swap file..."
mkswap "$SWAP_FILE"

# Enable swap
echo "Enabling swap..."
swapon "$SWAP_FILE"

# Add to /etc/fstab for persistence (if not already there)
if ! grep -q "^$SWAP_FILE" /etc/fstab; then
    echo "Adding swap file to /etc/fstab..."
    echo "$SWAP_FILE none swap sw 0 0" >> /etc/fstab
else
    echo "Swap file already in /etc/fstab"
fi

# Verify
echo ""
echo "Swap setup complete!"
echo "Current swap status:"
free -h
echo ""
swapon --show
