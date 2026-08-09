#!/usr/bin/env bash
# Echo /odom from any directory (CycloneDDS eth0; ignore stale ros2 daemon).
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
set +u
# shellcheck source=/dev/null
source "${PROJECT_DIR}/scripts/setup.eth0.sh" >/dev/null
set -u
ros2 daemon stop >/dev/null 2>&1 || true
exec ros2 topic echo --no-daemon --qos-reliability reliable \
  /odom nav_msgs/msg/Odometry "$@"
