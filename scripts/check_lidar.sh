#!/usr/bin/env zsh
# Quick Unitree lidar visibility check (run on the machine that runs go2-nav).
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "${SCRIPT_DIR}/install/setup.zsh"
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI="${CYCLONEDDS_URI:-file://${SCRIPT_DIR}/cyclonedds.eth0.xml}"

echo "CYCLONEDDS_URI=$CYCLONEDDS_URI"
echo "ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-0}"
echo ""

topics=$(ros2 topic list 2>/dev/null | grep '^/utlidar' || true)
if [[ -z "$topics" ]]; then
  echo "No /utlidar/* topics found."
  echo "  • Ping the robot: ping -c1 10.1.108.250"
  echo "  • Match ROS_DOMAIN_ID on PC and dog (often 0)."
  echo "  • Enable LiDAR service on the Go2 (see Unitree LiDAR_service doc)."
  exit 1
fi

echo "UtliDAR topics:"
echo "$topics"
echo ""

for t in /utlidar/lidar_state /utlidar/cloud /utlidar/imu; do
  echo "--- $t ---"
  if echo "$topics" | grep -qx "$t"; then
    timeout 5 ros2 topic echo "$t" --once 2>&1 | head -35
  else
    echo "(not in topic list)"
  fi
  echo ""
done
