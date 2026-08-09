#!/usr/bin/env bash
# Compatibility wrapper — real logic lives in 02_cpu/.
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/02_cpu/cpu.sh" "$@"
