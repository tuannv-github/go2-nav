#!/bin/zsh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

source $SCRIPT_DIR/run_mqtt_to_ros2.sh.conf

cd $SCRIPT_DIR/joystick_controller
./venv/bin/python3 joystick_mqtt.py  --device $DEVICE --broker $MQTT_BROKER --port $MQTT_PORT --topic /wirelesscontroller 