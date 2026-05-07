#!/usr/bin/env bash
set -euo pipefail

echo "[cpu.sh] Enabling Jetson maximum performance profile..."

if ! command -v nvpmodel >/dev/null 2>&1; then
  echo "[cpu.sh] Error: nvpmodel not found. This script must run on Jetson." >&2
  exit 1
fi

if ! command -v jetson_clocks >/dev/null 2>&1; then
  echo "[cpu.sh] Error: jetson_clocks not found. This script must run on Jetson." >&2
  exit 1
fi

# MAXN is mode 0 on most Jetson devices.
sudo nvpmodel -m 0
sudo jetson_clocks

# Set fan to max speed if fan control utility exists.
if command -v jetson_clocks >/dev/null 2>&1; then
  sudo jetson_clocks --fan || true
fi

echo "[cpu.sh] Done. Device set to maximum performance."
