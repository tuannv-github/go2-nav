#!/bin/sh

# Project root (this file lives in scripts/)
if [ -n "${BASH_SOURCE[0]:-}" ]; then
  _src="${BASH_SOURCE[0]}"
elif [ -n "${ZSH_VERSION:-}" ]; then
  eval '_src="${(%):-%x}"'
else
  _src="$0"
fi
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$_src")/.." && pwd)"
unset _src


echo "Setup unitree ros2 environment"
if [ -n "$BASH_VERSION" ]; then
  source "$SCRIPT_DIR/install/setup.bash"
elif [ -n "$ZSH_VERSION" ]; then
  source "$SCRIPT_DIR/install/setup.zsh"
else
  source "$SCRIPT_DIR/install/setup.sh"
fi

export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI="file://${SCRIPT_DIR}/cyclonedds/cyclonedds.wlan0.xml"
