#!/usr/bin/env bash
# Snapshot the live RTAB-Map session into map/ (or a custom directory).
#
# While rtabmap is running this:
#   1. Calls /rtabmap/backup  →  <repo>/map/rtabmap.db.back  (in-memory graph)
#   2. Saves /map             →  <outdir>/map.pgm + map.yaml
#   3. If <outdir> != map/, also copies the .back file to <outdir>/rtabmap.db
#
# Existing files that would be overwritten are renamed <file>.bk.YYYYMMDD
# first (same-day collision → .bk.YYYYMMDDHHMMSS).
#
# Localization still loads map/rtabmap.db. After you stop mapping, rtabmap
# writes that file on shutdown. To localize from a mid-session snapshot without
# a clean shutdown: stop rtabmap, then cp map/rtabmap.db.back map/rtabmap.db.
#
# Usage:
#   ./scripts/save_map.sh                 # write occupancy into <repo>/map
#   ./scripts/save_map.sh ~/maps/lab1     # occupancy + db copy there
#   ./scripts/save_map.sh -h
#
# Env:
#   MAP_TOPIC      default /map
#   RTABMAP_NODE   default /rtabmap
#   ROS2_SETUP     default <repo>/scripts/setup.sh
#   DB_PATH        default <repo>/map/rtabmap.db  (live DB; backup is DB_PATH.back)
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
MAP_DIR="${PROJECT_ROOT_DIR}/map"
ROS2_SETUP="${ROS2_SETUP:-${SCRIPT_DIR}/setup.sh}"
MAP_TOPIC="${MAP_TOPIC:-/map}"
RTABMAP_NODE="${RTABMAP_NODE:-/rtabmap}"
DB_PATH="${DB_PATH:-${MAP_DIR}/rtabmap.db}"
DB_BACK="${DB_PATH}.back"

usage() {
  sed -n '2,27p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
}

# Move an existing file aside as <name>.bk.YYYYMMDD before overwrite.
backup_if_exists() {
  local src="$1"
  [[ -e "${src}" ]] || return 0
  local dest="${src}.bk.${DATE_TAG}"
  if [[ -e "${dest}" ]]; then
    dest="${src}.bk.$(date +%Y%m%d%H%M%S)"
  fi
  echo "  Keeping previous: ${src} → ${dest}"
  mv -f "${src}" "${dest}"
}

[[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && usage

OUTPUT_DIR="${1:-${MAP_DIR}}"
DATE_TAG="$(date +%Y%m%d)"
BACKUP_SVC="${RTABMAP_NODE%/}/backup"
# ros2 service names are absolute
[[ "${BACKUP_SVC}" == /* ]] || BACKUP_SVC="/${BACKUP_SVC}"

setup_ros() {
  if [[ ! -f "${ROS2_SETUP}" ]]; then
    echo "error: missing ROS setup: ${ROS2_SETUP}" >&2
    exit 1
  fi
  set +u
  # shellcheck disable=SC1090
  source "${ROS2_SETUP}" >/dev/null
  set -u
}

service_exists() {
  ros2 service list 2>/dev/null | grep -qx "$1"
}

topic_exists() {
  ros2 topic list 2>/dev/null | grep -qx "$1"
}

mkdir -p "${OUTPUT_DIR}"
setup_ros

echo "=========================================="
echo "Saving current map"
echo "=========================================="
echo "Output directory: ${OUTPUT_DIR}"
echo "Map topic:        ${MAP_TOPIC}"
echo "Backup service:   ${BACKUP_SVC}"
echo "Live database:    ${DB_PATH}"
echo ""

# --- RTAB-Map database (in-memory → .back) ---
echo "Step 1: Flush RTAB-Map database via ${BACKUP_SVC}"
echo "        (can take a while on a multi-GB db; mapping pauses during backup)"
if ! service_exists "${BACKUP_SVC}"; then
  echo "✗ ${BACKUP_SVC} is not available"
  echo "  Start mapping first, e.g. startup/tmux.livox.mapping.sh"
  exit 1
fi

backup_if_exists "${DB_BACK}"

if ros2 service call "${BACKUP_SVC}" std_srvs/srv/Empty; then
  echo "✓ Backup service returned ok"
  if [[ -f "${DB_BACK}" ]]; then
    echo "  Snapshot: ${DB_BACK}  ($(du -h "${DB_BACK}" | awk '{print $1}'))"
  else
    echo "⚠ ${DB_BACK} was not created — check rtabmap database_path"
  fi
else
  echo "✗ Failed to call ${BACKUP_SVC}"
  exit 1
fi
echo ""

# --- Occupancy grid ---
echo "Step 2: Save occupancy grid from ${MAP_TOPIC}"
if ! topic_exists "${MAP_TOPIC}"; then
  echo "✗ Topic ${MAP_TOPIC} is not being published"
  exit 1
fi

MAP_STEM="${OUTPUT_DIR}/map"
backup_if_exists "${MAP_STEM}.pgm"
backup_if_exists "${MAP_STEM}.yaml"
if ros2 run nav2_map_server map_saver_cli -f "${MAP_STEM}" \
    --ros-args -p map_topic:="${MAP_TOPIC}"; then
  echo "✓ Occupancy map saved"
  echo "  ${MAP_STEM}.pgm"
  echo "  ${MAP_STEM}.yaml"
else
  echo "✗ map_saver_cli failed"
  exit 1
fi
echo ""

# Copy db snapshot when saving somewhere other than the live map/ dir.
if [[ "$(cd "${OUTPUT_DIR}" && pwd)" != "$(cd "${MAP_DIR}" && pwd)" ]]; then
  if [[ -f "${DB_BACK}" ]]; then
    echo "Step 3: Copy database snapshot → ${OUTPUT_DIR}/rtabmap.db"
    backup_if_exists "${OUTPUT_DIR}/rtabmap.db"
    cp -a "${DB_BACK}" "${OUTPUT_DIR}/rtabmap.db"
    echo "✓ ${OUTPUT_DIR}/rtabmap.db"
  else
    echo "Step 3: skipped (no ${DB_BACK})"
  fi
  echo ""
fi

echo "=========================================="
echo "✓ Current map saved"
echo "=========================================="
echo "Occupancy:  ${MAP_STEM}.pgm / ${MAP_STEM}.yaml"
echo "RTAB-Map:   ${DB_BACK}"
echo "Live DB:    ${DB_PATH}  (updated on rtabmap shutdown)"
