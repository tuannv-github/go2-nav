#!/usr/bin/env bash
# Zero /odom via /odom_ext_relay/reset (FastDDS). Does not change Unitree pose.
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

set +u
# shellcheck source=/dev/null
source /opt/ros/humble/setup.bash
if [[ -f "${PROJECT_DIR}/install/setup.bash" ]]; then
  # shellcheck source=/dev/null
  source "${PROJECT_DIR}/install/setup.bash"
fi
set -u

export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
export ROS_LOCALHOST_ONLY=0

# shellcheck source=/dev/null
source "${SCRIPT_DIR}/fastrtps_odom_ext.sh"
fastrtps_write_odom_ext_xml "${PROJECT_DIR}" || true

exec ros2 service call /odom_ext_relay/reset std_srvs/srv/Empty
