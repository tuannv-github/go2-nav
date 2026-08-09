#!/usr/bin/env bash
# Apply Jetson maximum performance: nvpmodel MAXN + locked clocks + max fan.
#
# Usage:
#   ./cpu.sh              # apply (sudo if not root)
#   ./cpu.sh status       # print current nvpmodel + clocks
#
set -euo pipefail

MODE_ID="${CPU_NVPMODEL_MODE:-0}"   # 0 = MAXN on Orin NX
MODE_NAME="${CPU_NVPMODEL_NAME:-MAXN}"

usage() {
  sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'
  exit 1
}

run_root() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
  else
    sudo "$@"
  fi
}

query_mode_id() {
  # nvpmodel -q prints: "NV Power Mode: NAME" then the numeric id on the next line.
  nvpmodel -q 2>/dev/null | awk 'NR==2 {print $1; exit}'
}

print_status() {
  echo "=== nvpmodel ==="
  nvpmodel -q 2>/dev/null || echo "(nvpmodel query failed)"
  echo
  echo "=== jetson_clocks ==="
  if [[ "$(id -u)" -eq 0 ]]; then
    jetson_clocks --show
  else
    sudo jetson_clocks --show
  fi
}

cmd="${1:-apply}"
case "$cmd" in
  -h|--help|help) usage ;;
  status|show|query) print_status; exit 0 ;;
  apply|"") ;;
  *)
    echo "error: unknown command: $cmd" >&2
    usage
    ;;
esac

echo "[02_cpu] Enabling Jetson ${MODE_NAME} (nvpmodel -m ${MODE_ID}) + max clocks..."

if ! command -v nvpmodel >/dev/null 2>&1; then
  echo "[02_cpu] Error: nvpmodel not found. This script must run on Jetson." >&2
  exit 1
fi
if ! command -v jetson_clocks >/dev/null 2>&1; then
  echo "[02_cpu] Error: jetson_clocks not found. This script must run on Jetson." >&2
  exit 1
fi

current="$(query_mode_id || true)"
if [[ "${current}" == "${MODE_ID}" ]]; then
  echo "[02_cpu] nvpmodel already ${MODE_NAME} (${MODE_ID})"
else
  # Do not pass --force: that can reboot the robot. Answer 'n' if nvpmodel asks.
  if ! printf 'n\n' | run_root nvpmodel -m "${MODE_ID}"; then
    echo "[02_cpu] Warning: nvpmodel -m ${MODE_ID} failed; continuing with jetson_clocks." >&2
  fi
fi

run_root jetson_clocks
run_root jetson_clocks --fan || true

echo "[02_cpu] Done. Device set to maximum performance."
print_status
