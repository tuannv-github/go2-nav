#!/bin/zsh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

source $SCRIPT_DIR/setup.sh
source $SCRIPT_DIR/run_mqtt_to_ros2.sh.conf

ros2 run joystick_controller mqtt_to_ros2_bridge.py --ros-args -p mqtt_broker:=$MQTT_BROKER -p mqtt_port:=$MQTT_PORT
