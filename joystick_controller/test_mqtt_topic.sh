#!/bin/zsh
#
# Test script to subscribe to MQTT topic and display joystick messages
#

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Source config file for MQTT settings
source $SCRIPT_DIR/run_mqtt_to_ros2.sh.conf

# Check for virtual environment
VENV_PYTHON=""
if [ -f "$SCRIPT_DIR/venv/bin/python3" ]; then
    VENV_PYTHON="$SCRIPT_DIR/venv/bin/python3"
    echo "Using virtual environment Python: $VENV_PYTHON"
elif [ -d "$SCRIPT_DIR/venv" ]; then
    echo "Warning: venv directory exists but python3 not found"
fi

# Default topic if not specified
MQTT_TOPIC="${1:-/wirelesscontroller}"

echo "Subscribing to MQTT topic: $MQTT_TOPIC"
echo "MQTT Broker: $MQTT_BROKER:$MQTT_PORT"
echo "Press Ctrl+C to stop"
echo ""

# Check if mosquitto_sub is available
if command -v mosquitto_sub &> /dev/null; then
    mosquitto_sub -h "$MQTT_BROKER" -p "$MQTT_PORT" -t "$MQTT_TOPIC" -v
elif [ -n "$VENV_PYTHON" ]; then
    # Use venv Python if available
    $VENV_PYTHON << EOF
import paho.mqtt.client as mqtt
import json
import sys

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print(f"✓ Connected to MQTT broker")
        client.subscribe("$MQTT_TOPIC")
        print(f"✓ Subscribed to topic: $MQTT_TOPIC")
    else:
        print(f"✗ Failed to connect, return code {rc}")
        sys.exit(1)

def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode('utf-8')
        data = json.loads(payload)
        print(f"[{msg.topic}] {json.dumps(data, indent=2)}")
    except json.JSONDecodeError:
        print(f"[{msg.topic}] {msg.payload.decode('utf-8')}")

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message

try:
    client.connect("$MQTT_BROKER", $MQTT_PORT, 60)
    client.loop_forever()
except KeyboardInterrupt:
    print("\nStopping...")
    client.disconnect()
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
EOF
elif command -v python3 &> /dev/null; then
    # Fallback to system Python if venv not available
    python3 << EOF
import paho.mqtt.client as mqtt
import json
import sys

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print(f"✓ Connected to MQTT broker")
        client.subscribe("$MQTT_TOPIC")
        print(f"✓ Subscribed to topic: $MQTT_TOPIC")
    else:
        print(f"✗ Failed to connect, return code {rc}")
        sys.exit(1)

def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode('utf-8')
        data = json.loads(payload)
        print(f"[{msg.topic}] {json.dumps(data, indent=2)}")
    except json.JSONDecodeError:
        print(f"[{msg.topic}] {msg.payload.decode('utf-8')}")

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message

try:
    client.connect("$MQTT_BROKER", $MQTT_PORT, 60)
    client.loop_forever()
except KeyboardInterrupt:
    print("\nStopping...")
    client.disconnect()
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
EOF
else
    echo "Error: Neither mosquitto_sub nor python3 with paho-mqtt found"
    echo "Please install one of:"
    echo "  - mosquitto-clients (apt-get install mosquitto-clients)"
    echo "  - python3-paho-mqtt (pip install paho-mqtt)"
    echo "Or ensure venv is set up: ./setup.sh"
    exit 1
fi
