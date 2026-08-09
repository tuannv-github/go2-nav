#!/usr/bin/env bash
# Echo /odom on the external discovery tag (all-NIC bus).
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
set +u
# shellcheck source=/dev/null
source "${PROJECT_DIR}/install/setup.bash"
set -u
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
export CYCLONEDDS_URI="file://${PROJECT_DIR}/cyclonedds/cyclonedds.odom-ext.xml"
ros2 daemon stop >/dev/null 2>&1 || true
exec ros2 topic echo --no-daemon --qos-reliability reliable \
  /odom nav_msgs/msg/Odometry "$@"
