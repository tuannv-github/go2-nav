#!/bin/bash

# colcon build --symlink-install --packages-select go2-nav
colcon build --symlink-install --packages-select joystick_controller unitree_go

# colcon build --symlink-install
