#!/usr/bin/env bash
# Launch utlidar_odom on eth0 + ext relay (named pipe -> all-NIC DDS).
# Do not use `set -u` here: colcon install/setup.bash uses unset vars.
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
export GO2_NAV_ROOT="${PROJECT_DIR}"

if [[ -f "${PROJECT_DIR}/install/setup.bash" ]]; then
  # shellcheck source=/dev/null
  source "${PROJECT_DIR}/install/setup.bash"
elif [[ -f "${PROJECT_DIR}/install/setup.zsh" ]]; then
  # shellcheck source=/dev/null
  source "${PROJECT_DIR}/install/setup.zsh"
else
  echo "install/setup.bash not found; run: colcon build --packages-select odom" >&2
  exit 1
fi

export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
export CYCLONEDDS_ETH0_URI="file://${PROJECT_DIR}/cyclonedds/cyclonedds.eth0.xml"
export CYCLONEDDS_EXT_URI="file://${PROJECT_DIR}/cyclonedds/cyclonedds.odom-ext.xml"
export CYCLONEDDS_URI="${CYCLONEDDS_ETH0_URI}"

wait_iface() {
  local ifc=$1 max=${2:-90} i
  for i in $(seq 1 "$max"); do
    if ip -o link show "$ifc" 2>/dev/null | grep -q 'state UP'; then
      echo "interface $ifc is UP"
      return 0
    fi
    echo "waiting for $ifc ($i/$max)..."
    sleep 1
  done
  echo "warning: $ifc not UP after ${max}s" >&2
  return 1
}
wait_iface eth0 90 || true
wait_iface wlan0 30 || true

# FastDDS ext /odom: bind wlan IP + unicast peer (WiFi multicast is slow).
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/fastrtps_odom_ext.sh"
if fastrtps_write_odom_ext_xml "${PROJECT_DIR}"; then
  echo "FastDDS ext wlan=${WLAN_IP} peer=${PEER_IP}"
else
  echo "warning: no wlan0 IPv4; FastDDS ext will use all interfaces" >&2
fi

exec ros2 launch odom odom.launch.py "$@"
