#!/usr/bin/env bash
# Reverse SSH tunnel: remote LISTEN_PORT -> this host :22
#
#   ssh -N -v -R 4123:localhost:22 master
#
# Usage:
#   ./run_tunnel.sh           # foreground (systemd / manual)
#   ./run_tunnel.sh status    # show local ssh process
#
set -euo pipefail

# Host alias from ~/.ssh/config (User/HostName/IdentityFile live there).
REMOTE_HOST="${SSH_TUNNEL_HOST:-master}"
LISTEN_PORT="${SSH_TUNNEL_LISTEN_PORT:-4123}"
LOCAL_PORT="${SSH_TUNNEL_LOCAL_PORT:-22}"
VERBOSE="${SSH_TUNNEL_VERBOSE:-1}"
IDENTITY="${SSH_TUNNEL_IDENTITY:-}"

usage() {
  sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'
  exit 1
}

print_status() {
  echo "tunnel: ${REMOTE_HOST}  -R ${LISTEN_PORT}:localhost:${LOCAL_PORT}"
  if pgrep -af "[s]sh .* -R ${LISTEN_PORT}:localhost:${LOCAL_PORT}" >/dev/null; then
    pgrep -af "[s]sh .* -R ${LISTEN_PORT}:localhost:${LOCAL_PORT}"
  else
    echo "(not running)"
    return 1
  fi
}

cmd="${1:-run}"
case "$cmd" in
  -h|--help|help) usage ;;
  status|show)
    print_status
    exit $?
    ;;
  run|"") ;;
  *)
    echo "error: unknown command: $cmd" >&2
    usage
    ;;
esac

if ! command -v ssh >/dev/null 2>&1; then
  echo "[03_ssh] Error: ssh not found." >&2
  exit 1
fi

# Drop a leftover manual tunnel so remote LISTEN_PORT is free.
if pgrep -f "[s]sh .* -R ${LISTEN_PORT}:localhost:${LOCAL_PORT}" >/dev/null; then
  echo "[03_ssh] Stopping stale local ssh -R ${LISTEN_PORT}..."
  pkill -f "[s]sh .* -R ${LISTEN_PORT}:localhost:${LOCAL_PORT}" || true
  sleep 1
fi

SSH_OPTS=(
  -N
  -o BatchMode=yes
  -o IdentitiesOnly=yes
  -o IdentityAgent=none
  -o ExitOnForwardFailure=yes
  -o ServerAliveInterval=30
  -o ServerAliveCountMax=3
  -o StrictHostKeyChecking=accept-new
  -R "${LISTEN_PORT}:localhost:${LOCAL_PORT}"
)
if [[ -n "${IDENTITY}" ]]; then
  if [[ ! -f "${IDENTITY}" ]]; then
    echo "[03_ssh] Error: identity file not found: ${IDENTITY}" >&2
    exit 1
  fi
  SSH_OPTS+=(-i "${IDENTITY}" -o "IdentityFile=${IDENTITY}")
fi
if [[ "${VERBOSE}" == "1" ]]; then
  SSH_OPTS+=(-v)
fi

echo "[03_ssh] ssh ${SSH_OPTS[*]} ${REMOTE_HOST}"
exec ssh "${SSH_OPTS[@]}" "${REMOTE_HOST}"
