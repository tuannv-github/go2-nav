# shellcheck shell=bash
# Write /tmp/fastrtps.odom-ext.xml from @WLAN_IP@ / @PEER_IP@ tokens.
# WLAN from wlan0; peer from ODOM_EXT_PEER (default roboticpc).
fastrtps_write_odom_ext_xml() {
  local project_dir="${1:?}"
  local wlan_ip peer_ip template runtime
  wlan_ip="$(ip -4 -o addr show wlan0 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -1 || true)"
  peer_ip="${ODOM_EXT_PEER:-10.1.100.139}"
  template="${project_dir}/fastrtps/fastrtps.odom-ext.xml"
  runtime="/tmp/fastrtps.odom-ext.xml"
  if [[ -z "${wlan_ip}" || ! -f "${template}" ]]; then
    unset FASTRTPS_DEFAULT_PROFILES_FILE || true
    return 1
  fi
  sed -e "s/@WLAN_IP@/${wlan_ip}/g" -e "s/@PEER_IP@/${peer_ip}/g" \
    "${template}" >"${runtime}"
  export FASTRTPS_DEFAULT_PROFILES_FILE="${runtime}"
  export WLAN_IP="${wlan_ip}"
  export PEER_IP="${peer_ip}"
}
