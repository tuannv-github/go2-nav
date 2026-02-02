#!/bin/zsh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Default values
MQTT_BROKER="localhost"
MQTT_PORT="1883"
DEVICE=""
MAX_X_SPEED="0.5"
MAX_Y_SPEED="0.5"
MAX_YAW_SPEED="0.5"

# Source config file if it exists to override defaults
if [ -f "$SCRIPT_DIR/run_mqtt_to_ros2.sh.conf" ]; then
    source "$SCRIPT_DIR/run_mqtt_to_ros2.sh.conf"
else
    echo "Warning: $SCRIPT_DIR/run_mqtt_to_ros2.sh.conf not found, using default values."
fi

cd "$SCRIPT_DIR"

# Build device argument if DEVICE is set
DEVICE_ARG=""
if [ -n "$DEVICE" ]; then
    DEVICE_ARG="--device $DEVICE"
    echo "Using configured device: $DEVICE"
else
    echo "Auto-detecting joystick device..."
    # List available devices first
    echo "Available joystick devices:"
    ./venv/bin/python3 list_joystick_devices.py
    echo ""
fi

echo "Starting joystick to MQTT publisher..."
echo "MQTT Broker: $MQTT_BROKER:$MQTT_PORT"
echo "MQTT Topic: /wirelesscontroller"
echo "Max Speeds: X=$MAX_X_SPEED, Y=$MAX_Y_SPEED, Yaw=$MAX_YAW_SPEED"
echo ""

# Run the publisher
./venv/bin/python3 joystick_mqtt.py $DEVICE_ARG \
    --broker "$MQTT_BROKER" \
    --port "$MQTT_PORT" \
    --topic /wirelesscontroller \
    --max-x-speed "$MAX_X_SPEED" \
    --max-y-speed "$MAX_Y_SPEED" \
    --max-yaw-speed "$MAX_YAW_SPEED"