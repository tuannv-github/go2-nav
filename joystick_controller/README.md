# Joystick to MQTT Publisher

A Python program that reads joystick input and publishes the state to an MQTT topic.

## Requirements

- Python 3.6+
- Linux (for evdev support)
- Joystick/gamepad connected to the system

## Installation

### Option 1: Using Virtual Environment (Recommended)

```bash
# Run the setup script
./setup.sh

# Or manually:
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Option 2: System Packages (Ubuntu/Debian)

```bash
sudo apt-get update
sudo apt-get install python3-evdev python3-paho-mqtt
```

### Option 3: Using pipx

```bash
pipx install evdev paho-mqtt
```

## Usage

### If using virtual environment

```bash
source venv/bin/activate
python3 joystick_mqtt.py
```

### Or run directly with venv Python

```bash
./venv/bin/python3 joystick_mqtt.py
```

### Basic usage (auto-detect joystick)

```bash
python3 joystick_mqtt.py
```

### Specify joystick device

```bash
python3 joystick_mqtt.py --device /dev/input/js0
```

### Custom MQTT broker and topic

```bash
python3 joystick_mqtt.py --broker mqtt.example.com --port 1883 --topic joystick/xbox360
```

### With MQTT authentication

```bash
python3 joystick_mqtt.py --username myuser --password mypass
```

### All options

```bash
python3 joystick_mqtt.py \
    --device /dev/input/js0 \
    --broker localhost \
    --port 1883 \
    --topic joystick/state \
    --username myuser \
    --password mypass \
    --interval 0.1
```

## Command Line Arguments

- `--device, -d`: Joystick device path (e.g., `/dev/input/js0`). Auto-detects if not specified
- `--broker, -b`: MQTT broker address (default: `localhost`)
- `--port, -p`: MQTT broker port (default: `1883`)
- `--topic, -t`: MQTT topic to publish to (default: `joystick/state`)
- `--username, -u`: MQTT username (optional)
- `--password, -P`: MQTT password (optional)
- `--interval, -i`: Publish interval in seconds (default: `0.1`)

## Output Format

The program publishes JSON messages to the MQTT topic with the following format:

```json
{
    "axes": {
        "ABS_X": 0.0,
        "ABS_Y": 0.0,
        "ABS_RX": 0.0,
        "ABS_RY": 0.0,
        "ABS_Z": 0.0,
        "ABS_RZ": 0.0
    },
    "buttons": {
        "BTN_SOUTH": 0,
        "BTN_EAST": 0,
        "BTN_NORTH": 0,
        "BTN_WEST": 0
    },
    "timestamp": 1234567890.123
}
```

- `axes`: Analog stick and trigger values normalized to range [-1.0, 1.0]
- `buttons`: Button states (0 = released, 1 = pressed)
- `timestamp`: Unix timestamp of the event

## Finding Your Joystick Device

To find your joystick device:

```bash
# List input devices
ls -la /dev/input/

# Or use jstest
jstest /dev/input/js0

# Or check dmesg for device connection
dmesg | grep -i joystick
```

For Xbox 360 controllers, the device might appear as `/dev/input/event*` instead of `/dev/input/js*`.
