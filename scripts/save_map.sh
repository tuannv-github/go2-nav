#!/bin/bash
# Script to save RTAB-Map database and Nav2 occupancy grid map

readonly SAVE_MAP_SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
readonly PROJECT_ROOT_DIR="$(cd "${SAVE_MAP_SCRIPT_DIR}/.." && pwd)"
readonly MAP_DIR="${PROJECT_ROOT_DIR}/map"

# Default output path is ../map relative to script directory
OUTPUT_DIR="${1:-${MAP_DIR}}"
MAP_TOPIC="${MAP_TOPIC:-/map}"
RTABMAP_NODE="${RTABMAP_NODE:-rtabmap}"

# Create map directory if it doesn't exist
mkdir -p "${OUTPUT_DIR}"

echo "=========================================="
echo "Saving RTAB-Map database and Nav2 map..."
echo "=========================================="
echo "Output directory: ${OUTPUT_DIR}"
echo "Map topic: ${MAP_TOPIC}"
echo "RTAB-Map node: ${RTABMAP_NODE}"
echo ""

# Save RTAB-Map database using backup service, then copy to output directory
echo "Step 1: Saving RTAB-Map database..."
if ros2 service call ${RTABMAP_NODE}/backup std_srvs/srv/Empty; then
    echo "✓ RTAB-Map database backup service called successfully"
else
    echo "⚠ Warning: Could not call RTAB-Map backup service"
fi
echo ""

# Save Nav2 occupancy map
echo "Step 2: Saving Nav2 occupancy grid map..."
MAP_NAME=$(basename "${OUTPUT_DIR}")
MAP_PATH="${OUTPUT_DIR}/${MAP_NAME}"
if ros2 run nav2_map_server map_saver_cli -f "${MAP_PATH}" --ros-args -p map_topic:=${MAP_TOPIC} > /dev/null 2>&1; then
    echo "✓ Nav2 occupancy map saved successfully!"
    echo "  Files: ${MAP_PATH}.pgm, ${MAP_PATH}.yaml"
else
    echo "✗ Failed to save Nav2 occupancy map"
    echo "  Make sure the map topic ${MAP_TOPIC} is being published"
    exit 1
fi

echo ""
echo "=========================================="
echo "✓ All maps saved successfully!"
echo "=========================================="
