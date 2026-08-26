#!/bin/bash
# Helper script to connect to robot via reverse SSH tunnel
# This script should be run ON THE SERVER (10.1.101.211)
# It connects via localhost:2200 since GatewayPorts may not be enabled

source common.sh

echo "Connecting to robot via reverse SSH tunnel..."
echo "Note: This script must be run on the server ($SERVER_IP_ADDRESS)"
echo ""

CMD="ssh -p $SERVER_PORT $ROBOT_USER_NAME@localhost"
echo "Running: $CMD"
echo ""

$CMD

