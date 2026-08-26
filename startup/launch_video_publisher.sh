#!/usr/bin/env bash
# Launch Realsense Video Publisher node with CycloneDDS configuration.
# Docs: docs/architecture.md
# Uses cyclonedds/cyclonedds.video.xml for strictly local DDS communication.
# Do not use `set -u` here: colcon `install/setup.bash` uses unset vars (e.g. COLCON_TRACE).
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ -f "${PROJECT_DIR}/install/setup.bash" ]]; then
  # shellcheck source=/dev/null
  source "${PROJECT_DIR}/install/setup.bash"
elif [[ -f "${PROJECT_DIR}/install/setup.zsh" ]]; then
  # shellcheck source=/dev/null
  source "${PROJECT_DIR}/install/setup.zsh"
else
  echo "install/setup.bash not found; run colcon build from ${PROJECT_DIR}" >&2
  exit 1
fi

export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI="file://${PROJECT_DIR}/cyclonedds/cyclonedds.video.xml"

exec ros2 launch realsense_video_publisher video_publisher.launch.py "$@"
