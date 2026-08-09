#!/usr/bin/env bash
# Print ROS /cmd_vel (Nav2 / test path) as compact vx vy wz + expected sticks.
#
# Usage:
#   ./scripts/print_cmd_vel.sh
#   ./scripts/print_cmd_vel.sh --topic /cmd_vel
#   ./scripts/print_cmd_vel.sh --raw
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PRINT_PY="${SCRIPT_DIR}/print_cmd_vel.py"

set +u
# shellcheck source=/dev/null
source "${ROOT}/scripts/setup.sh"
set -u

exec python3 "${PRINT_PY}" "$@"
