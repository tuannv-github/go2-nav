#!/bin/zsh

readonly RUN_MQTT_TO_ROS2_SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "RUN_MQTT_TO_ROS2_SCRIPT_DIR: $RUN_MQTT_TO_ROS2_SCRIPT_DIR"

PROJECT_DIR=$RUN_MQTT_TO_ROS2_SCRIPT_DIR/../

export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI="file://${PROJECT_DIR}/cyclonedds/cyclonedds.go2.xml"

source $PROJECT_DIR/install/setup.zsh
source $RUN_MQTT_TO_ROS2_SCRIPT_DIR/run_mqtt_to_ros2.sh.conf

ros2 run joystick_controller mqtt_to_ros2_bridge.py --ros-args -p mqtt_broker:=$MQTT_BROKER -p mqtt_port:=$MQTT_PORT
