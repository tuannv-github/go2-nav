#!/usr/bin/env bash
# Back-compat wrapper → test_controller_move.sh --action turn_right
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${SCRIPT_DIR}/test_controller_move.sh" --action turn_right "$@"
