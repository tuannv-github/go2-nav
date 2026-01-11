#!/bin/bash
# Quick script to check timestamps of IMU and camera topics

echo "=== Checking IMU and Camera Timestamps ==="
echo ""
echo "Press Ctrl+C to stop"
echo ""

# Function to get timestamp from a message
get_timestamp() {
    topic=$1
    timeout 2 ros2 topic echo --once $topic 2>/dev/null | grep -A 1 "stamp:" | grep -E "(sec|nanosec)" | head -2
}

echo "--- IMU Topic: /utlidar/imu ---"
echo "Checking for messages..."
ros2 topic echo --once /utlidar/imu 2>/dev/null | grep -A 3 "header:" | head -5
echo ""

echo "--- Camera Color Topic: /input/camera/camera/color/image_raw ---"
echo "Checking for messages..."
ros2 topic echo --once /input/camera/camera/color/image_raw 2>/dev/null | grep -A 3 "header:" | head -5
echo ""

echo "--- Topic Info ---"
echo "IMU topic info:"
ros2 topic info /utlidar/imu 2>/dev/null
echo ""
echo "Camera topic info:"
ros2 topic info /input/camera/camera/color/image_raw 2>/dev/null
echo ""

echo "--- Topic Hz (rate) ---"
echo "IMU rate (checking for 5 seconds):"
timeout 5 ros2 topic hz /utlidar/imu 2>/dev/null || echo "No IMU messages received"
echo ""
echo "Camera rate (checking for 5 seconds):"
timeout 5 ros2 topic hz /input/camera/camera/color/image_raw 2>/dev/null || echo "No camera messages received"
