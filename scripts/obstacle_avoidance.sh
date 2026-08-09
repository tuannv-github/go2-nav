#!/usr/bin/env bash
# Switch Go2 obstacle avoidance via /api/obstacles_avoid.
#
# Usage:
#   ./scripts/obstacle_avoidance.sh              # toggle
#   ./scripts/obstacle_avoidance.sh status       # print current state
#   ./scripts/obstacle_avoidance.sh on|off       # force enable/disable
#   ./scripts/obstacle_avoidance.sh toggle       # flip current state
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROS2_SETUP="${ROS2_SETUP:-$SCRIPT_DIR/setup.eth0.sh}"

API_SET=1001
API_GET=1002
TOPIC_REQ=/api/obstacles_avoid/request
TOPIC_RESP=/api/obstacles_avoid/response

usage() {
  sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
  exit 1
}

setup_ros() {
  if [[ ! -f "$ROS2_SETUP" ]]; then
    echo "error: missing ROS setup: $ROS2_SETUP" >&2
    exit 1
  fi
  # ROS/ament setup scripts reference unset vars; relax nounset while sourcing.
  set +u
  # shellcheck disable=SC1090
  source "$ROS2_SETUP" >/dev/null
  set -u
}

# Publish one Request and capture the next matching Response (by api_id).
# Prints response data JSON to stdout.
call_api() {
  local api_id="$1"
  local parameter="$2"
  local req_id
  req_id="$(date +%s%N | cut -c1-15)"
  local tmp
  tmp="$(mktemp)"

  timeout 8 ros2 topic echo --once --full-length \
    --qos-reliability reliable --qos-durability volatile \
    "$TOPIC_RESP" >"$tmp" 2>/dev/null &
  local echo_pid=$!
  sleep 0.8

  timeout 10 ros2 topic pub --once -w 1 \
    --qos-reliability reliable --qos-durability volatile \
    "$TOPIC_REQ" unitree_api/msg/Request "{
    header: {
      identity: { id: ${req_id}, api_id: ${api_id} },
      lease: { id: 0 },
      policy: { priority: 0, noreply: false }
    },
    parameter: '${parameter}',
    binary: []
  }" >/dev/null || true

  wait "$echo_pid" 2>/dev/null || true

  if [[ ! -s "$tmp" ]]; then
    rm -f "$tmp"
    echo "error: no response from $TOPIC_RESP (is the robot on DDS/eth0?)" >&2
    exit 1
  fi

  local status data
  status="$(awk '/^  status:/{getline; if ($1=="code:") print $2}' "$tmp" | head -1)"
  data="$(awk -F"'" '/^data:/{print $2; exit}' "$tmp")"
  rm -f "$tmp"

  if [[ "${status:-}" != "0" ]]; then
    echo "error: api_id=${api_id} status=${status:-unknown} data=${data:-}" >&2
    exit 1
  fi
  printf '%s\n' "$data"
}

get_enable() {
  local data
  data="$(call_api "$API_GET" '{}')"
  # data like {"enable":true} or {"enable":false}
  if [[ "$data" == *'true'* ]]; then
    echo "true"
  elif [[ "$data" == *'false'* ]]; then
    echo "false"
  else
    echo "error: unexpected SwitchGet data: $data" >&2
    exit 1
  fi
}

set_enable() {
  local enable="$1" # true|false
  call_api "$API_SET" "{\"enable\":${enable}}" >/dev/null
}

cmd="${1:-toggle}"
case "$cmd" in
  -h|--help|help) usage ;;
esac

setup_ros

case "$cmd" in
  status|get)
    enable="$(get_enable)"
    if [[ "$enable" == "true" ]]; then
      echo "obstacle_avoidance: ON"
    else
      echo "obstacle_avoidance: OFF"
    fi
    ;;
  on|enable|true|1)
    set_enable true
    enable="$(get_enable)"
    echo "obstacle_avoidance: ON (set=${enable})"
    ;;
  off|disable|false|0)
    set_enable false
    enable="$(get_enable)"
    echo "obstacle_avoidance: OFF (set=${enable})"
    ;;
  toggle|switch|"")
    cur="$(get_enable)"
    if [[ "$cur" == "true" ]]; then
      set_enable false
      echo "obstacle_avoidance: OFF (was ON)"
    else
      set_enable true
      echo "obstacle_avoidance: ON (was OFF)"
    fi
    ;;
  *)
    echo "error: unknown command: $cmd" >&2
    usage
    ;;
esac
