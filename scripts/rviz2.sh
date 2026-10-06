#!/usr/bin/env bash
# Run rviz2 on the master with CycloneDDS on the 10.1.100.220 interface only.
# Do not use `set -u`: sourcing ROS setup.bash touches unset variables.
set -eo pipefail

MASTER_IP="10.1.100.220"
ROBOT_PEER="10.1.100.210"

if [[ -f /opt/ros/humble/setup.bash ]]; then
  # shellcheck source=/dev/null
  source /opt/ros/humble/setup.bash
else
  echo "ROS Humble not found at /opt/ros/humble" >&2
  exit 1
fi

if ! ros2 pkg prefix rmw_cyclonedds_cpp >/dev/null 2>&1; then
  echo "rmw_cyclonedds_cpp is not installed. Install ros-humble-rmw-cyclonedds-cpp." >&2
  exit 1
fi

IFACE="$(ip -4 -o addr show | awk -v ip="${MASTER_IP}/" 'index($4, ip) == 1 { print $2; exit }')"
if [[ -z "${IFACE}" ]]; then
  echo "No interface has address ${MASTER_IP}" >&2
  exit 1
fi

CFG="$(mktemp /tmp/cyclonedds.master.XXXXXX.xml)"
trap 'rm -f "${CFG}"' EXIT
cat > "${CFG}" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<CycloneDDS>
  <Domain id="any">
    <General>
      <Interfaces>
        <NetworkInterface name="${IFACE}" priority="default" multicast="true" />
      </Interfaces>
    </General>
    <Discovery>
      <Peers>
        <Peer address="${ROBOT_PEER}"/>
      </Peers>
    </Discovery>
  </Domain>
</CycloneDDS>
EOF

export ROS_LOCALHOST_ONLY=0
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI="file://${CFG}"

echo "rviz2 CycloneDDS iface=${IFACE} (${MASTER_IP}) peer=${ROBOT_PEER}"
exec rviz2 "$@"
