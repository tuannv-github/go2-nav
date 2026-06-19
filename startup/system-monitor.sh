#!/usr/bin/env bash
# Append system health / kernel / GPU stats to log files for post-watchdog analysis.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="${SYSTEM_MONITOR_LOG_DIR:-$PROJECT_DIR/logs}"
MONITOR_LOG="$LOG_DIR/system-monitor.log"
TEGRA_LOG="$LOG_DIR/tegrastats.log"
KERNEL_LOG="$LOG_DIR/kernel-live.log"

mkdir -p "$LOG_DIR"

TEGRA_PID=""
JOURNAL_PID=""
STOPPING=0

append_line() {
    local file="$1"
    shift
    local line="[$(date '+%Y-%m-%d %H:%M:%S')] $*"
    echo "$line"
    printf '%s\n' "$line" >> "$file"
}

log() {
    append_line "$MONITOR_LOG" "$@"
}

cleanup() {
    if [[ "$STOPPING" -eq 1 ]]; then
        return
    fi
    STOPPING=1
    local code=$?
    log "monitor stopping (exit=${code})"
    [[ -n "$TEGRA_PID" ]] && kill "$TEGRA_PID" 2>/dev/null || true
    [[ -n "$JOURNAL_PID" ]] && kill "$JOURNAL_PID" 2>/dev/null || true
    wait "$TEGRA_PID" "$JOURNAL_PID" 2>/dev/null || true
}

trap cleanup EXIT
trap 'cleanup; exit 130' INT
trap 'cleanup; exit 143' TERM

log "=== monitor start pid=$$ log_dir=${LOG_DIR} ==="
log "uptime: $(uptime -p 2>/dev/null || uptime)"
log "boot_time: $(who -b 2>/dev/null | awk '{$1=""; sub(/^ /,""); print}' || echo unknown)"

while IFS= read -r line; do
    log "reset_reason: ${line}"
done < <(dmesg -T 2>/dev/null | grep -E 'PMC reset|BCCPLEXWDT|kernel panic|Out of memory' || true)

if [[ -w /proc/sys/kernel/hung_task_timeout_secs ]]; then
    if echo 20 > /proc/sys/kernel/hung_task_timeout_secs 2>/dev/null; then
        log "hung_task_timeout_secs=20"
    fi
elif command -v sudo >/dev/null 2>&1; then
    if sudo -n sh -c 'echo 20 > /proc/sys/kernel/hung_task_timeout_secs' 2>/dev/null; then
        log "hung_task_timeout_secs=20 (via sudo)"
    else
        log "hung_task_timeout_secs unchanged (need root)"
    fi
fi

if command -v tegrastats >/dev/null 2>&1; then
    log "tegrastats -> ${TEGRA_LOG}"
    {
        printf '\n=== tegrastats start %s ===\n' "$(date '+%Y-%m-%d %H:%M:%S')"
        tegrastats --interval 1000
    } >> "$TEGRA_LOG" 2>&1 &
    TEGRA_PID=$!
else
    log "tegrastats not found, skipping"
fi

if command -v journalctl >/dev/null 2>&1; then
    log "journalctl -kf -> ${KERNEL_LOG}"
    {
        printf '\n=== journalctl start %s ===\n' "$(date '+%Y-%m-%d %H:%M:%S')"
        journalctl -kf -n 0
    } >> "$KERNEL_LOG" 2>&1 &
    JOURNAL_PID=$!
else
    log "journalctl not found, skipping"
fi

log "monitor running (tegrastats_pid=${TEGRA_PID:-none} journal_pid=${JOURNAL_PID:-none})"

if [[ -n "$TEGRA_PID" || -n "$JOURNAL_PID" ]]; then
    wait $TEGRA_PID $JOURNAL_PID 2>/dev/null || true
fi
