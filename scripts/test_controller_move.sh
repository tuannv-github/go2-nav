#!/usr/bin/env bash
# Test go2_controller drive + yaw (default: all six motions on ROS /cmd_vel).
#
# Usage:
#   ./scripts/test_controller_move.sh
#   ./scripts/test_controller_move.sh --action all
#   ./scripts/test_controller_move.sh --action forward --distance 1.0 --v 0.2
#   ./scripts/test_controller_move.sh --action left --distance 0.4 --v 0.2
#   ./scripts/test_controller_move.sh --action right --distance 0.4 --v 0.2
#   ./scripts/test_controller_move.sh --action turn_left --angle 90 --w 0.5
#   ./scripts/test_controller_move.sh --action turn_right --angle 90 --w 0.5
#   ./scripts/test_controller_move.sh --via rest
#   ./scripts/test_controller_move.sh --via wireless
#
# --via ros       Nav2 path: /cmd_vel → /wirelesscontroller
# --via rest      POST /cmd_vel sport Move
# --via wireless  POST /wireless sticks
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TEST_PY="${SCRIPT_DIR}/test_controller_move.py"

set +u
# shellcheck source=/dev/null
source "${ROOT}/scripts/setup.sh"
set -u

exec python3 "${TEST_PY}" "$@"
