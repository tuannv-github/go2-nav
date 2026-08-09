#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

# colcon build --symlink-install --packages-select go2-nav
colcon build --symlink-install --packages-select go2_controller unitree_go

# colcon build --symlink-install
