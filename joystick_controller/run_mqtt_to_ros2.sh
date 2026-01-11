#!/bin/zsh

readonly RUN_MQTT_TO_ROS2_SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "RUN_MQTT_TO_ROS2_SCRIPT_DIR: $RUN_MQTT_TO_ROS2_SCRIPT_DIR"

source $RUN_MQTT_TO_ROS2_SCRIPT_DIR/../setup.sh
source $RUN_MQTT_TO_ROS2_SCRIPT_DIR/run_mqtt_to_ros2.sh.conf

ros2 run joystick_controller mqtt_to_ros2_bridge.py --ros-args -p mqtt_broker:=$MQTT_BROKER -p mqtt_port:=$MQTT_PORT
