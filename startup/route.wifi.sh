#!/bin/bash
# Host routes via WiFi gateway (FCCLab wlan0).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=route.common.sh
source "$SCRIPT_DIR/route.common.sh"

route_delete_all

route_add_host "$IP_VIDEO_MQTT_BROKER" "$IP_WIFI_GATEWAY"
route_add_host "$IP_LLM_SERVER" "$IP_WIFI_GATEWAY"
route_add_host "$IP_LOCATION_SERVER" "$IP_WIFI_GATEWAY"
