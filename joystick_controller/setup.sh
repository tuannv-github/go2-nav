#!/bin/bash
# Setup script for joystick_controller

set -e

echo "Setting up joystick_controller..."

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "Setup complete!"
echo ""
echo "To use the program:"
echo "  source venv/bin/activate"
echo "  python3 joystick_mqtt.py"
echo ""
echo "Or run directly:"
echo "  ./venv/bin/python3 joystick_mqtt.py"
