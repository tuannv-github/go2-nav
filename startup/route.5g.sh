#!/bin/bash
# Host routes via 5G / USB tether gateway.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=route.common.sh
source "$SCRIPT_DIR/route.common.sh"

route_delete_all

route_add_host "$IP_VIDEO_MQTT_BROKER" "$IP_5G_GATEWAY"
route_add_host "$IP_LLM_SERVER" "$IP_5G_GATEWAY"
