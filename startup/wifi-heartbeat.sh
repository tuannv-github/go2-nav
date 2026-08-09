#!/usr/bin/env bash
# Monitor wlan0 and reconnect to the SSID in wifi.info via nmcli when needed.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
INFO_FILE="${SCRIPT_DIR}/wifi.info"
LOG_FILE="${WIFI_HEARTBEAT_LOG:-${PROJECT_DIR}/logs/wifi-heartbeat.log}"
RETRY_SLEEP_SEC=3

mkdir -p "$(dirname "$LOG_FILE")"

read_wifi_info() {
    local key="$1"
    local line value
    if [[ ! -f "$INFO_FILE" ]]; then
        echo "missing wifi info file: $INFO_FILE" >&2
        exit 1
    fi
    line="$(grep -E "^[[:space:]]*${key}:" "$INFO_FILE" | tail -n 1 || true)"
    if [[ -z "$line" ]]; then
        echo "missing '${key}' in $INFO_FILE" >&2
        exit 1
    fi
    value="${line#*:}"
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    printf '%s' "$value"
}

INTERFACE="$(read_wifi_info interface)"
SSID="$(read_wifi_info ssid)"
PASSWORD="$(read_wifi_info password)"

STATS_RECONNECTS=0
STATS_RECOVER_STARTS=0
STATS_WIFI_CONNECT_ATTEMPTS=0

wifi_radio_state() {
    nmcli radio wifi 2>/dev/null || echo "unknown"
}

iface_link_state() {
    if ip link show "$INTERFACE" 2>/dev/null | grep -q 'state UP'; then
        echo "up"
    else
        echo "down"
    fi
}

nmcli_iface_state() {
    local state
    state="$(nmcli -t -f DEVICE,STATE device status 2>/dev/null \
        | awk -F: -v dev="$INTERFACE" '$1 == dev { print $2; exit }')"
    if [[ -n "$state" ]]; then
        echo "$state"
    else
        echo "unknown"
    fi
}

current_connection() {
    nmcli -t -f DEVICE,TYPE,STATE,CONNECTION device status 2>/dev/null \
        | awk -F: -v dev="$INTERFACE" '$1 == dev && $3 == "connected" { print $4; exit }'
}

radio_ok() {
    [[ "$(wifi_radio_state)" == "enabled" ]]
}

iface_ok() {
    [[ "$(iface_link_state)" == "up" ]]
}

wifi_ok() {
    local state conn
    state="$(nmcli_iface_state)"
    conn="$(current_connection)"
    [[ "$state" == "connected" && "$conn" == "$SSID" ]]
}

health_issues() {
    local issues=()

    if ! radio_ok; then
        issues+=("radio=$(wifi_radio_state)")
    fi
    if ! iface_ok; then
        issues+=("iface=$(iface_link_state)")
    fi
    if ! wifi_ok; then
        local state conn
        state="$(nmcli_iface_state)"
        conn="$(current_connection)"
        if [[ "$state" != "connected" ]]; then
            issues+=("nmcli=${state}")
        else
            issues+=("ssid=${conn:-none}")
        fi
    fi

    if ((${#issues[@]} > 0)); then
        local IFS=';'
        echo "${issues[*]}"
    fi
}

is_healthy() {
    radio_ok && iface_ok && wifi_ok
}

emit_log() {
    local line="$1"
    echo "$line"
    printf '%s\n' "$line" >> "$LOG_FILE"
}

log_status() {
    local status="$1"
    local detail="${2:-}"
    local ts radio iface nmcli_state conn stats line
    ts="$(date '+%Y-%m-%d %H:%M:%S')"
    radio="$(wifi_radio_state)"
    iface="$(iface_link_state)"
    nmcli_state="$(nmcli_iface_state)"
    conn="$(current_connection)"
    stats="reconnects=${STATS_RECONNECTS} recover_starts=${STATS_RECOVER_STARTS} wifi_connect_attempts=${STATS_WIFI_CONNECT_ATTEMPTS}"
    if [[ -n "$detail" ]]; then
        line="[${ts}] interface=${INTERFACE} ssid=${SSID} password=${PASSWORD} radio=${radio} iface=${iface} nmcli=${nmcli_state} current_ssid=${conn:-none} status=${status} ${stats} ${detail}"
    else
        line="[${ts}] interface=${INTERFACE} ssid=${SSID} password=${PASSWORD} radio=${radio} iface=${iface} nmcli=${nmcli_state} current_ssid=${conn:-none} status=${status} ${stats}"
    fi
    emit_log "$line"
}

log_action() {
    log_status "disconnected" "doing=${1} cmd=${2}"
}

log_result() {
    local doing="$1"
    local cmd="$2"
    local ok="$3"
    local msg="$4"
    if [[ "$ok" == "ok" ]]; then
        log_status "disconnected" "done=${doing} cmd=${cmd} result=ok msg=${msg}"
    else
        log_status "disconnected" "done=${doing} cmd=${cmd} result=failed msg=${msg}"
    fi
}

# NetworkManager needs polkit "network-control"; fall back to passwordless sudo.
run_nmcli() {
    local doing="$1"
    shift
    local cmd="nmcli $*"
    local out

    log_action "$doing" "$cmd"
    if out="$(nmcli "$@" 2>&1)"; then
        log_result "$doing" "$cmd" ok "${out:-success}"
        return 0
    fi

    log_status "disconnected" "doing=${doing} cmd=sudo -n ${cmd} reason=need_privilege prev_err=${out}"
    if out="$(sudo -n nmcli "$@" 2>&1)"; then
        log_result "$doing" "$cmd" ok "${out:-success_via_sudo}"
        return 0
    fi

    log_result "$doing" "$cmd" failed "${out}"
    return 1
}

run_cmd() {
    local doing="$1"
    shift
    local cmd="$*"
    local out

    log_action "$doing" "$cmd"
    if out="$("$@" 2>&1)"; then
        log_result "$doing" "$cmd" ok "${out:-success}"
        return 0
    fi

    log_result "$doing" "$cmd" failed "${out}"
    return 1
}

disconnect_interface() {
    local conn
    conn="$(current_connection)"
    if [[ -z "$conn" ]]; then
        log_status "disconnected" "doing=skip_disconnect reason=already_disconnected"
        return 0
    fi

    if run_nmcli disconnect_device device disconnect "$INTERFACE"; then
        return 0
    fi

    run_nmcli disconnect_connection connection down id "$conn"
}

ensure_radio_on() {
    local attempt=0
    while ! radio_ok; do
        attempt=$((attempt + 1))
        log_status "disconnected" "step=1_radio attempt=${attempt} goal=radio_enabled current=$(wifi_radio_state)"
        run_nmcli enable_networking networking on || true
        run_nmcli enable_wifi_radio radio wifi on || true
        sleep "$RETRY_SLEEP_SEC"
    done
    if ((attempt > 0)); then
        log_status "disconnected" "step=1_radio_done attempts=${attempt} radio=$(wifi_radio_state)"
    fi
}

ensure_iface_up() {
    local attempt=0
    while ! iface_ok; do
        attempt=$((attempt + 1))
        log_status "disconnected" "step=2_iface attempt=${attempt} goal=iface_up current=$(iface_link_state)"
        run_nmcli set_managed device set "$INTERFACE" managed yes || true
        run_nmcli enable_networking networking on || true
        if ! run_cmd link_up ip link set "$INTERFACE" up; then
            log_action "link_up_sudo" "sudo -n ip link set ${INTERFACE} up"
            sudo -n ip link set "$INTERFACE" up >/dev/null 2>&1 \
                && log_result "link_up_sudo" "sudo -n ip link set ${INTERFACE} up" ok success \
                || log_result "link_up_sudo" "sudo -n ip link set ${INTERFACE} up" failed denied
        fi
        sleep "$RETRY_SLEEP_SEC"
    done
    if ((attempt > 0)); then
        log_status "disconnected" "step=2_iface_done attempts=${attempt} iface=$(iface_link_state)"
    fi
}

ensure_correct_ssid_or_disconnected() {
    local attempt=0 conn
    while true; do
        conn="$(current_connection)"
        if [[ -z "$conn" || "$conn" == "$SSID" ]]; then
            break
        fi
        attempt=$((attempt + 1))
        log_status "disconnected" "step=3_wrong_ssid attempt=${attempt} goal=disconnect current=${conn} expected=${SSID}"
        disconnect_interface || true
        sleep "$RETRY_SLEEP_SEC"
    done
    if ((attempt > 0)); then
        conn="$(current_connection)"
        log_status "disconnected" "step=3_wrong_ssid_done attempts=${attempt} current_ssid=${conn:-none}"
    fi
}

ensure_wifi_connected() {
    local attempt=0
    while ! is_healthy; do
        attempt=$((attempt + 1))
        STATS_WIFI_CONNECT_ATTEMPTS=$((STATS_WIFI_CONNECT_ATTEMPTS + 1))
        log_status "disconnected" "step=4_wifi_connect attempt=${attempt} goal=connect_to_${SSID} issues=$(health_issues)"
        run_nmcli wifi_connect device wifi connect "$SSID" password "$PASSWORD" ifname "$INTERFACE" || true
        sleep 2
        if is_healthy; then
            log_status "connected" "step=4_wifi_connect_done attempts=${attempt}"
            return 0
        fi
        log_status "disconnected" "step=4_wifi_connect_retry attempt=${attempt} issues=$(health_issues) retry_in=${RETRY_SLEEP_SEC}s"
        sleep "$RETRY_SLEEP_SEC"
    done
}

recover_until_connected() {
    STATS_RECOVER_STARTS=$((STATS_RECOVER_STARTS + 1))
    log_status "disconnected" "recover_start issues=$(health_issues)"
    ensure_radio_on
    ensure_iface_up
    ensure_correct_ssid_or_disconnected
    ensure_wifi_connected
    apply_route_script
    STATS_RECONNECTS=$((STATS_RECONNECTS + 1))
    log_status "connected" "recover_done"
}

apply_route_script() {
    if [[ -z "${ROUTE_SCRIPT:-}" || ! -f "$ROUTE_SCRIPT" ]]; then
        return 0
    fi
    log_status "connected" "doing=apply_routes script=${ROUTE_SCRIPT}"
    if bash "$ROUTE_SCRIPT"; then
        log_status "connected" "done=apply_routes result=ok"
    else
        log_status "disconnected" "done=apply_routes result=failed"
    fi
}

log_status "connected" "event=start pid=$$ log_file=${LOG_FILE}"
if is_healthy; then
    apply_route_script
fi

while true; do
    if ! radio_ok; then
        log_status "disconnected" "check=radio failed radio=$(wifi_radio_state)"
        ensure_radio_on
    fi

    if is_healthy; then
        log_status "connected"
        sleep 1
    else
        log_status "disconnected" "check=health failed issues=$(health_issues)"
        recover_until_connected
    fi
done
