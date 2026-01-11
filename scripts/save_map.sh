#!/bin/bash
# Simple script to save RTAB-Map occupancy grid map

readonly SAVE_MAP_SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

OUTPUT_PATH="${1:-map}"
MAP_TOPIC="${MAP_TOPIC:-/map}"

echo "Saving RTAB-Map occupancy grid map..."
echo "Output: ${OUTPUT_PATH}.pgm and ${OUTPUT_PATH}.yaml"
echo "Map topic: ${MAP_TOPIC}"

# Use Python script to save the map
python3 "$SAVE_MAP_SCRIPT_DIR/save_occupancy_map.py" --output "$OUTPUT_PATH" --map-topic "$MAP_TOPIC"

if [ $? -eq 0 ]; then
    echo "✓ Map saved successfully!"
    echo "  Files: ${OUTPUT_PATH}.pgm, ${OUTPUT_PATH}.yaml"
else
    echo "✗ Failed to save map"
    exit 1
fi
