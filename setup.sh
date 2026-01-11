#!/bin/sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"


echo "Setup unitree ros2 environment"
source $SCRIPT_DIR/install/setup.zsh

export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI="file://${SCRIPT_DIR}/cyclonedds.xml"
