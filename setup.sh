#!/bin/sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"


echo "Setup unitree ros2 environment"
source $SCRIPT_DIR/install/setup.zsh

export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI='<CycloneDDS><Domain><General><Interfaces>
                        <NetworkInterface name="eth0" priority="default" multicast="default" />
                        </Interfaces></General></Domain></CycloneDDS>'
