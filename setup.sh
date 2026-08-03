#!/bin/sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"


echo "Setup unitree ros2 environment"
if [ -n "$BASH_VERSION" ]; then
  source "$SCRIPT_DIR/install/setup.bash"
elif [ -n "$ZSH_VERSION" ]; then
  source "$SCRIPT_DIR/install/setup.zsh"
else
  source "$SCRIPT_DIR/install/setup.sh"
fi

export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
# CycloneDDS peers (see cyclonedds.xml): 10.1.108.250, 10.1.100.139
export CYCLONEDDS_URI="file://${SCRIPT_DIR}/cyclonedds.xml"
