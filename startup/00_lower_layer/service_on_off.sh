#!/usr/bin/env bash
# Enable/disable Go2 onboard (lower-layer) mapping / avoidance.
#
# Usage:
#   ./service_on_off.sh off [--retry]     # stop USLAM + matching robot_state services
#   ./service_on_off.sh on [--retry]      # re-enable those robot_state services
#   ./service_on_off.sh status            # print robot_state list (highlight targets)
#   ./service_on_off.sh list              # print all robot_state services
#   ./service_on_off.sh switch NAME 0|1   # switch one robot_state service
#
# Default robot_state names (override with LOWER_LAYER_SERVICES):
#   unitree_lidar_slam voxel_height_mapping
# Do not ServiceSwitch obstacles_avoid — that kills /api/obstacles_avoid.
# sport_mode / unitree_lidar / obstacles_avoid are never switched.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ROS2_SETUP="${ROS2_SETUP:-$REPO_ROOT/scripts/setup.eth0.sh}"
RETRY_SECS="${RETRY_SECS:-180}"
RETRY_INTERVAL="${RETRY_INTERVAL:-5}"

API_SWITCH=1001
API_LIST=1003
TOPIC_REQ=/api/robot_state/request
TOPIC_RESP=/api/robot_state/response

DEFAULT_SERVICES=(unitree_lidar_slam voxel_height_mapping slam uslam)
PROTECTED_NEVER=(sport_mode unitree_lidar obstacles_avoid)

RETRY=0
ARGS=()
for a in "$@"; do
  case "$a" in
    --retry) RETRY=1 ;;
    -h|--help|help) ARGS=(help) ;;
    *) ARGS+=("$a") ;;
  esac
done
set -- "${ARGS[@]+"${ARGS[@]}"}"
cmd="${1:-off}"

usage() {
  sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'
  exit 1
}

log() { echo "[lower_layer] $*"; }
warn() { echo "[lower_layer] WARN: $*" >&2; }

is_never() {
  local n="$1" p
  for p in "${PROTECTED_NEVER[@]}"; do
    [[ "${n,,}" == "${p,,}" ]] && return 0
  done
  return 1
}

wanted_services() {
  if [[ -n "${LOWER_LAYER_SERVICES:-}" ]]; then
    # shellcheck disable=SC2206
    echo $LOWER_LAYER_SERVICES
  else
    echo "${DEFAULT_SERVICES[*]}"
  fi
}

is_wanted() {
  local n="$1" w
  for w in $(wanted_services); do
    [[ "${n,,}" == "${w,,}" ]] && return 0
  done
  return 1
}

setup_ros() {
  if [[ ! -f "$ROS2_SETUP" ]]; then
    echo "error: missing ROS setup: $ROS2_SETUP" >&2
    exit 1
  fi
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

  timeout 8 ros2 topic pub --once -w 1 \
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

  if [[ ! -s "$tmp" ]] || ! grep -q "api_id: ${api_id}" "$tmp" 2>/dev/null; then
    rm -f "$tmp"
    echo "error: no matching response from $TOPIC_RESP (api_id=${api_id})" >&2
    return 1
  fi

  local data
  data="$(python3 - "$tmp" <<'PY'
import re, sys
text = open(sys.argv[1], encoding="utf-8", errors="replace").read()
m = re.search(r"(?m)^data:\s*(.*)$", text)
if not m:
    raise SystemExit(1)
val = m.group(1).strip()
if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
    val = val[1:-1]
val = val.replace(r"\'", "'").replace(r'\"', '"')
if not val:
    raise SystemExit(1)
print(val)
PY
)" || {
    rm -f "$tmp"
    echo "error: could not parse data from $TOPIC_RESP" >&2
    return 1
  }
  rm -f "$tmp"
  printf '%s\n' "$data"
}

service_list_raw() {
  call_api "$API_LIST" '{}'
}

# stdin: ServiceList JSON array → lines: name<TAB>status<TAB>protect
parse_list() {
  python3 -c '
import json, sys
raw = sys.stdin.read().strip()
if not raw:
    raise SystemExit("empty ServiceList payload")
obj = json.loads(raw)
if not isinstance(obj, list):
    raise SystemExit("expected JSON array from ServiceList")
for s in obj:
    print("{}\t{}\t{}".format(s.get("name", ""), s.get("status", ""), s.get("protect", "")))
'
}

service_switch() {
  local name="$1" swit="$2"
  if is_never "$name"; then
    warn "refusing to switch protected service: $name"
    return 1
  fi
  local data
  data="$(call_api "$API_SWITCH" "{\"name\":\"${name}\",\"switch\":${swit}}")"
  log "ServiceSwitch name=${name} switch=${swit} data=${data}"
}

uslam_cmd() {
  local payload="$1"
  timeout 5 ros2 topic pub --once -w 0 /uslam/client_command std_msgs/msg/String \
    "{data: '${payload}'}" >/dev/null 2>&1 || true
}

avoidance_feature() {
  local mode="$1"
  local av="$REPO_ROOT/scripts/obstacle_avoidance.sh"
  if [[ -x "$av" ]]; then
    "$av" "$mode" || warn "obstacle_avoidance.sh $mode failed"
  fi
}

print_list() {
  local highlight="${1:-0}"
  local raw name status protect mark rows
  raw="$(service_list_raw)"
  rows="$(printf '%s\n' "$raw" | parse_list)"
  printf '%-24s %-8s %s\n' "NAME" "STATUS" "PROTECT"
  while IFS=$'\t' read -r name status protect; do
    [[ -z "$name" ]] && continue
    mark=""
    if (( highlight )) && is_wanted "$name"; then
      mark="  <-- target"
    fi
    printf '%-24s %-8s %s%s\n' "$name" "$status" "$protect" "$mark"
  done <<<"$rows"
}

switch_wanted() {
  local swit="$1"
  local raw name status protect rows
  raw="$(service_list_raw)" || return 1
  rows="$(printf '%s\n' "$raw" | parse_list)" || {
    echo "error: ServiceList JSON parse failed" >&2
    return 1
  }
  local found=0 failed=0
  while IFS=$'\t' read -r name status protect; do
    [[ -z "$name" ]] && continue
    is_wanted "$name" || continue
    found=1
    if [[ "${protect}" == "1" ]]; then
      warn "skip protected service: $name"
      continue
    fi
    if ! service_switch "$name" "$swit"; then
      warn "switch failed: $name"
      failed=1
    fi
  done <<<"$rows"
  if (( found == 0 )); then
    echo "error: no matching robot_state services among: $(wanted_services)" >&2
    return 1
  fi
  (( failed == 0 ))
}

do_off() {
  log "stopping lower-layer mapping / avoidance"
  uslam_cmd '{"type":"nav","cmd":"endMapping"}'
  uslam_cmd '{"type":"nav","cmd":"closeSlam"}'
  switch_wanted 0 || return 1
  avoidance_feature off
  log "done (off)"
}

do_on() {
  log "enabling lower-layer services: $(wanted_services)"
  switch_wanted 1 || return 1
  avoidance_feature on
  log "done (on) — USLAM mapping is not auto-started"
}

run_cmd() {
  setup_ros
  case "$cmd" in
    help) usage ;;
    list)
      print_list 0
      ;;
    status|get)
      print_list 1
      ;;
    off|disable|stop|0)
      do_off
      ;;
    on|enable|start|1)
      do_on
      ;;
    switch)
      local name="${2:-}" swit="${3:-}"
      if [[ -z "$name" || -z "$swit" ]]; then
        echo "usage: $0 switch NAME 0|1" >&2
        exit 1
      fi
      service_switch "$name" "$swit"
      ;;
    *)
      echo "error: unknown command: $cmd" >&2
      usage
      ;;
  esac
}

case "$cmd" in
  -h|--help|help) usage ;;
esac

if (( RETRY )); then
  deadline=$((SECONDS + RETRY_SECS))
  while true; do
    if run_cmd "$@"; then
      exit 0
    fi
    if (( SECONDS >= deadline )); then
      echo "error: giving up after ${RETRY_SECS}s" >&2
      exit 1
    fi
    log "retry in ${RETRY_INTERVAL}s (DDS/robot not ready) ..."
    sleep "$RETRY_INTERVAL"
  done
fi

run_cmd "$@"
