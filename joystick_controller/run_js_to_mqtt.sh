#!/bin/zsh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

source $SCRIPT_DIR/run_mqtt_to_ros2.sh.conf

cd $SCRIPT_DIR

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
    echo "Starting joystick to MQTT publisher (will auto-detect if device not specified)..."
fi

echo "MQTT Broker: $MQTT_BROKER:$MQTT_PORT"
echo "MQTT Topic: /wirelesscontroller"
echo ""

./venv/bin/python3 joystick_mqtt.py $DEVICE_ARG --broker $MQTT_BROKER --port $MQTT_PORT --topic /wirelesscontroller 