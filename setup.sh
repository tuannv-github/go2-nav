#!/bin/sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"


echo "Setup unitree ros2 environment"
source $SCRIPT_DIR/install/setup.zsh

export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
# CycloneDDS peers (see cyclonedds.xml): 10.1.108.250, 10.1.100.139
export CYCLONEDDS_URI="file://${SCRIPT_DIR}/cyclonedds.xml"
