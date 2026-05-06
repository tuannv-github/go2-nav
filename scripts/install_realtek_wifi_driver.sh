#!/usr/bin/env bash
# Install out-of-tree Realtek 88x2bu driver for TP-Link Archer T4U ver.3
# (USB 2357:0115, RTL8812BU / RTL8822BU). Kernel 5.10+ (incl. Jetson tegra).
#
# Bracket lines go to stderr; real command stdout/stderr are inherited (TTY-friendly).
#   DEBUG=1                - bash -x for this wrapper only
#   INSTALL_DRIVER_TRACE=1 - sh -x for upstream install-driver.sh
#
# If apt hangs on a PPA (e.g. Connecting to ppa.launchpadcontent.net):
#   sudo SKIP_APT_UPDATE=1 ./install_realtek_wifi_driver.sh   # skip refresh only
# Tuning:
#   APT_HTTP_TIMEOUT default 25s per connection; APT_UPDATE_MAX_SECONDS default 180 (hard cap).
# If apt fails with dpkg lock errors (unattended-upgrades, etc.), this script waits by default:
#   WAIT_DPKG_UNLOCK_SEC   default 720 (0 = skip wait).
#   DPKG_POLL_INTERVAL     default 15 seconds between WAIT log lines.

set -euo pipefail

CACHE_DIR="${XDG_CACHE_HOME:-${HOME}/.cache}/go2-nav/88x2bu-20210702"
REPO_URL="https://github.com/morrownr/88x2bu-20210702.git"
BRANCH="${BRANCH:-main}"
APT_HTTP_TIMEOUT="${APT_HTTP_TIMEOUT:-25}"
APT_UPDATE_MAX_SECONDS="${APT_UPDATE_MAX_SECONDS:-180}"
WAIT_DPKG_UNLOCK_SEC="${WAIT_DPKG_UNLOCK_SEC:-720}"
DPKG_POLL_INTERVAL="${DPKG_POLL_INTERVAL:-15}"

log() {
	printf '[install-realtek-wifi] %s\n' "$*" >&2
}

wait_for_package_manager_unlock() {
	# Root only; callers run after need_root.
	if [[ "${SKIP_DPKG_WAIT:-0}" == "1" ]] || [[ "${WAIT_DPKG_UNLOCK_SEC:-0}" -eq 0 ]]; then
		log "Skipping dpkg/apt lock wait (SKIP_DPKG_WAIT=1 or WAIT_DPKG_UNLOCK_SEC=0)."
		return 0
	fi

	local waited=0
	local max_wait="${WAIT_DPKG_UNLOCK_SEC}"

	if ! command -v fuser >/dev/null 2>&1; then
		log "WARN: 'fuser' not found (usually from package psmisc). Cannot detect dpkg locks; apt may fail if unattended-upgrade is running."
		return 0
	fi

	local poll="${DPKG_POLL_INTERVAL}"
	local f locks_busy summary slack step

	while (( waited < max_wait )); do
		locks_busy=()
		for f in /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock /var/cache/apt/archives/lock /var/lib/apt/lists/lock; do
			[[ -e "${f}" ]] || continue
			if fuser -s "${f}" 2>/dev/null; then
				locks_busy+=("${f}")
			fi
		done

		if ((${#locks_busy[@]} == 0)); then
			log "Package manager locks are free (checked with fuser)."
			return 0
		fi

		summary="$(for f in "${locks_busy[@]}"; do fuser "${f}" 2>/dev/null || true; done | tr -s '\n' ' ' | sed 's/ $//')"

		log "WAIT: dpkg/apt lock held (often unattended-upgrade). Busy: ${locks_busy[*]}; PIDs: ${summary}"
		slack=$((max_wait - waited))
		step="${poll}"
		((slack < step)) && step="${slack}"
		log "WAIT: (${waited}/${max_wait}s) sleeping ${step}s. Or SKIP_DPKG_WAIT=1 (risky while upgrades run)"
		sleep "${step}"
		waited=$((waited + step))
	done

	log "ERROR: dpkg/apt still locked after ${max_wait}s. Stop unattended-upgrades or retry later:"
	log "  ps -eo pid,cmd | egrep -e unattended|apt-get|dpkg"
	exit 1
}

need_root() {
	if [[ "${EUID}" -ne 0 ]]; then
		echo "Run with sudo, e.g.: sudo $0" >&2
		exit 1
	fi
}

debug_env() {
	log "---- environment (internal commands emit raw stdout/stderr below) ----"
	local build="/lib/modules/$(uname -r)/build"

	log "--- id ---"
	id || true

	log "--- env HOME USER SUDO_USER PWD PATH ---"
	( printf 'HOME=%q\nUSER=%q\nSUDO_USER=%q\nPWD=%q\nPATH=%s\n' \
		"${HOME:-}" "${USER:-}" "${SUDO_USER:-}" "${PWD:-}" "${PATH:-}" )

	log "--- uname -a ---"
	uname -a || true

	log "--- kernel modules build symlink: ${build} ---"
	if [[ ! -e "${build}" ]]; then
		log "MISSING (${build})"
	else
		readlink -f "${build}" || ls -la "${build}" || true
	fi

	if command -v gcc >/dev/null 2>&1; then
		log "--- command -v gcc ---"
		command -v gcc
		log "--- gcc --version ---"
		gcc --version || true
	else
		log "gcc: not found on PATH"
	fi

	if command -v make >/dev/null 2>&1; then
		log "--- command -v make ---"
		command -v make
		log "--- make --version ---"
		make --version || true
	else
		log "make: not found on PATH"
	fi

	if command -v dkms >/dev/null 2>&1; then
		log "--- dkms --version ---"
		dkms --version || true
		log "--- dkms status ---"
		dkms status || true
	else
		log "dkms: not installed (upstream will use non-dkms install)"
	fi

	if command -v lsusb >/dev/null 2>&1; then
		log "--- lsusb ---"
		lsusb || true
	else
		log "lsusb: not found"
	fi
	log "--- end environment dump ---"
}

run_apt_get_update() {
	# Prevent indefinite stall on unreachable mirrors/PPAs.
	local -a acquire_opts=(
		-o "Acquire::http::Timeout=${APT_HTTP_TIMEOUT}"
		-o "Acquire::https::Timeout=${APT_HTTP_TIMEOUT}"
		-o "Acquire::ftp::Timeout=${APT_HTTP_TIMEOUT}"
		-o Acquire::Retries=2
		-o Acquire::Languages=none
	)
	if [[ "${SKIP_APT_UPDATE:-0}" == "1" ]]; then
		log "SKIP_APT_UPDATE=1 - skipping apt-get update (indexes may be stale)"
		return 0
	fi
	log "--- apt-get update: per-fetch timeout ${APT_HTTP_TIMEOUT}s; total cap ${APT_UPDATE_MAX_SECONDS}s. If stuck, SKIP_APT_UPDATE=1 or fix PPAs under /etc/apt/sources.list.d/ ---"
	local update_cmd=(
		env DEBIAN_FRONTEND=noninteractive apt-get "${acquire_opts[@]}" update
	)
	if command -v timeout >/dev/null 2>&1; then
		if timeout --foreground "${APT_UPDATE_MAX_SECONDS}" "${update_cmd[@]}"; then
			return 0
		fi
		log "WARN: apt-get update failed or exceeded ${APT_UPDATE_MAX_SECONDS}s (continuing)."
		return 0
	fi
	log "WARN: 'timeout' not found; apt-get update may hang on bad repos."
	if ! "${update_cmd[@]}"; then
		log "WARN: apt-get update failed (continuing)."
	fi
	return 0
}

ensure_build_env() {
	local build="/lib/modules/$(uname -r)/build"
	log "check kernel headers: ${build}"
	if [[ ! -d "${build}" ]]; then
		log "ERROR: kernel headers missing for $(uname -r)."
		log "Install the package that provides ${build} (Jetson: L4T kernel headers)."
		exit 1
	fi
	log "kernel headers OK"
	if command -v apt-get >/dev/null 2>&1; then
		wait_for_package_manager_unlock
		run_apt_get_update
		wait_for_package_manager_unlock
		log "--- apt-get install build-essential bc git ---"
		local -a acquire_opts=(
			-o "Acquire::http::Timeout=${APT_HTTP_TIMEOUT}"
			-o "Acquire::https::Timeout=${APT_HTTP_TIMEOUT}"
			-o "Acquire::ftp::Timeout=${APT_HTTP_TIMEOUT}"
			-o Acquire::Retries=2
		)
		DEBIAN_FRONTEND=noninteractive apt-get "${acquire_opts[@]}" install \
			-y --no-install-recommends build-essential bc git
		log "--- apt finished ---"
	else
		log "no apt-get; assuming build tools already present"
	fi
}

fetch_driver() {
	log "--- mkdir -pv cache dir parent ---"
	mkdir -pv "$(dirname "${CACHE_DIR}")"
	if [[ ! -d "${CACHE_DIR}/.git" ]]; then
		log "--- git clone ${REPO_URL} branch=${BRANCH} -> ${CACHE_DIR} ---"
		git clone --progress --depth 1 --branch "${BRANCH}" "${REPO_URL}" "${CACHE_DIR}"
	else
		log "--- git refresh in ${CACHE_DIR} ---"
		git -C "${CACHE_DIR}" fetch --progress origin "${BRANCH}" --depth 1
		git -C "${CACHE_DIR}" checkout "${BRANCH}"
		git -C "${CACHE_DIR}" reset --hard "origin/${BRANCH}"
	fi
	log "--- git rev-parse; driver tree: ${CACHE_DIR} ---"
	git -C "${CACHE_DIR}" rev-parse HEAD || true
	git -C "${CACHE_DIR}" rev-parse --short HEAD || true
}

main() {
	if [[ "${DEBUG:-0}" == 1 ]]; then
		set -x
	fi
	need_root
	debug_env
	ensure_build_env
	fetch_driver
	log "--- cd ${CACHE_DIR} ---"
	cd "${CACHE_DIR}"
	log "--- pwd ---"
	pwd || true

	log "--- upstream install-driver.sh NoPrompt ---"
	local status
	if [[ "${INSTALL_DRIVER_TRACE:-0}" == "1" ]]; then
		set -- sh -x ./install-driver.sh NoPrompt
	else
		set -- sh ./install-driver.sh NoPrompt
	fi
	if ! "$@"; then
		status=$?
		log "ERROR: install-driver.sh failed with exit ${status}"
		log "Re-run with sudo DEBUG=1 $0 for wrapper trace or INSTALL_DRIVER_TRACE=1 for upstream sh -x."
		exit 1
	fi
	log "--- upstream install-driver.sh finished ---"

	log "--- modinfo 88x2bu ---"
	modinfo 88x2bu || log "WARN: modinfo 88x2bu failed - often normal until reboot or depmod."

	log "--- /sys/module/88x2bu ---"
	if [[ -e /sys/module/88x2bu ]]; then
		ls -la /sys/module/88x2bu || true
	else
		log "NOTE: sysfs 88x2bu absent yet - driver may not be loaded"
	fi

	log "Done. Plug the adapter (or re-plug), then: ip link show | grep wl  OR  nmcli device"
}

main "$@"
