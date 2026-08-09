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

# FastDDS ext /odom: bind wlan IP only + unicast peer (WiFi multicast is slow).
WLAN_IP="$(ip -4 -o addr show wlan0 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -1 || true)"
PEER_IP="${ODOM_EXT_PEER:-10.1.100.139}"
FASTDDS_XML="${PROJECT_DIR}/fastrtps/fastrtps.odom-ext.xml"
if [[ -n "${WLAN_IP}" && -f "${FASTDDS_XML}" ]]; then
  FASTRTPS_RUNTIME="/tmp/fastrtps.odom-ext.xml"
  sed -e "s/10.1.100.210/${WLAN_IP}/g" -e "s/10.1.100.139/${PEER_IP}/g" \
    "${FASTDDS_XML}" >"${FASTRTPS_RUNTIME}"
  export FASTRTPS_DEFAULT_PROFILES_FILE="${FASTRTPS_RUNTIME}"
  echo "FastDDS ext wlan=${WLAN_IP} peer=${PEER_IP}"
else
  echo "warning: no wlan0 IPv4; FastDDS ext will use all interfaces" >&2
fi

exec ros2 launch odom odom.launch.py "$@"
