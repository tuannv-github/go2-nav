#!/bin/bash
# startup/run_vlaa.sh
#
# Launch the VLAA voice/LLM client (app_robots/main.py) and dynamically hand
# the Blink500B2+ mic and the USB Composite speaker from PulseAudio to VLAA's
# direct ALSA path, then give them back to PulseAudio when VLAA exits.
#
# This is "Option 1" from fix_audio.md (dynamic Pulse handoff): instead of
# permanently telling Pulse to ignore those USB devices via a udev rule, we
# ask Pulse to suspend its ALSA card client only while VLAA is running.
#
# Env vars (override before invoking if needed):
#   VLAA_APP_ROBOTS           Path to VLAA app_robots tree (default: ~/vlaa/app_robots)
#   VLAA_PULSE_CARD_PATTERNS  ERE matching Pulse card names to hand over
#                             (default covers Blink500B2+ and the 0909:005b speaker)
#   VLAA_ALSA_SPEAKER_CARD    ALSA card index for the USB speaker (default: auto from
#                             /proc/asound/cards line containing "USB Composite Device")
#   VLAA_AUDIO_NICE           Nice for this shell + python tree (default: -20; needs
#                             startup/setup_audio_priority.sh + re-login)
#   VLAA_AUDIO_RT_PRIO        SCHED_FIFO for VLAA audio processes when supported
#                             (default: 80; set empty to disable)

set -u

VLAA_APP_ROBOTS="${VLAA_APP_ROBOTS:-$HOME/vlaa/app_robots}"
VLAA_PULSE_CARD_PATTERNS="${VLAA_PULSE_CARD_PATTERNS:-Blink500B2|10d6_4803|USB_Composite|0909_005b}"
VLAA_AUDIO_NICE="${VLAA_AUDIO_NICE:--20}"
VLAA_AUDIO_RT_PRIO="${VLAA_AUDIO_RT_PRIO:-80}"
export VLAA_AUDIO_NICE VLAA_AUDIO_RT_PRIO

log()  { echo "[run_vlaa] $*"; }
warn() { echo "[run_vlaa] WARN: $*" >&2; }

apply_shell_nice() {
    if ! renice -n "$VLAA_AUDIO_NICE" -p $$ >/dev/null 2>&1; then
        warn "Could not set nice $VLAA_AUDIO_NICE (run startup/setup_audio_priority.sh and re-login)."
        return 1
    fi
    log "Shell nice set to $VLAA_AUDIO_NICE (python + children inherit CFS priority)."
}
apply_shell_nice

list_target_cards() {
    pactl list short cards 2>/dev/null \
        | awk -v pat="$VLAA_PULSE_CARD_PATTERNS" '$2 ~ pat {print $2}'
}

# mode: 1 = suspend (release ALSA so VLAA can grab hw:),
#       0 = resume   (let Pulse re-attach to the ALSA card)
set_card_suspend() {
    local mode="$1"
    if ! command -v pactl >/dev/null 2>&1; then
        log "pactl not installed; skipping Pulse handoff (mode=$mode)."
        return 0
    fi
    local cards
    cards="$(list_target_cards)" || true
    if [ -z "$cards" ]; then
        if [ "$mode" = "1" ]; then
            log "No matching PulseAudio cards (Pulse may not be running) — nothing to suspend."
        fi
        return 0
    fi
    local card
    while IFS= read -r card; do
        [ -z "$card" ] && continue
        if [ "$mode" = "1" ]; then
            log "Suspending PulseAudio card so VLAA can take ALSA exclusive: $card"
        else
            log "Resuming PulseAudio card: $card"
        fi
        pactl suspend-card "$card" "$mode" 2>/dev/null \
            || warn "pactl suspend-card $card $mode failed"
    done <<<"$cards"
}

# Max out ALSA PCM on the USB Composite speaker so direct hw playback (PyAudio)
# is not left at a low hardware level after Pulse releases the card.
max_speaker_alsa_pcm() {
    local card="${VLAA_ALSA_SPEAKER_CARD:-}"
    if [ -z "$card" ] && [ -r /proc/asound/cards ]; then
        card=$(awk '/USB Composite Device/ {print $1; exit}' /proc/asound/cards) || true
    fi
    if [ -z "$card" ]; then
        warn "Could not detect ALSA speaker card (no 'USB Composite Device' in /proc/asound/cards); skip amixer PCM."
        return 0
    fi
    if ! command -v amixer >/dev/null 2>&1; then
        warn "amixer not installed; skipping ALSA PCM max for card $card."
        return 0
    fi
    log "Setting ALSA card $card PCM to 100% (max) for USB speaker..."
    if amixer -c "$card" sset PCM 100% unmute 2>/dev/null; then
        log "ALSA card $card: PCM set to 100%."
    elif amixer -c "$card" sset PCM 312 unmute 2>/dev/null; then
        log "ALSA card $card: PCM set to max step."
    else
        warn "amixer failed for card $card (device busy or no PCM control); you can set VLAA_ALSA_SPEAKER_CARD or run amixer when VLAA is stopped."
    fi
}

PYPID=""
RAN_CLEANUP=0
cleanup() {
    [ "$RAN_CLEANUP" -eq 1 ] && return 0
    RAN_CLEANUP=1
    if [ -n "${PYPID:-}" ] && kill -0 "$PYPID" 2>/dev/null; then
        log "Terminating VLAA child (pid=$PYPID)..."
        kill -TERM "$PYPID" 2>/dev/null || true
        local i
        for i in $(seq 1 30); do
            kill -0 "$PYPID" 2>/dev/null || break
            sleep 0.1
        done
        kill -KILL "$PYPID" 2>/dev/null || true
    fi
    set_card_suspend 0
}

trap cleanup EXIT
trap 'cleanup; exit 143' TERM HUP

if [ ! -d "$VLAA_APP_ROBOTS" ]; then
    warn "VLAA_APP_ROBOTS not found: $VLAA_APP_ROBOTS"
    exit 1
fi

cd "$VLAA_APP_ROBOTS"

# Wait until the Blink500B2+ mic is enumerated by ALSA + PyAudio. This is the
# same gate the tmux script used to call inline; running it here keeps all
# pre-VLAA setup in one place.
if [ -f app_go2/setup/wait_for_blink500b2.sh ]; then
    log "Waiting for Blink500B2+ mic to be ready..."
    bash app_go2/setup/wait_for_blink500b2.sh
else
    warn "wait_for_blink500b2.sh not found under $VLAA_APP_ROBOTS/app_go2/setup; skipping."
fi

# Hand the cards over to VLAA, then start it. Background python so we keep a
# pid for clean shutdown via the EXIT/TERM traps above.
set_card_suspend 1

max_speaker_alsa_pcm

log "Starting VLAA: python3 main.py --robot-model go2"
python3 main.py --robot-model go2 &
PYPID=$!
wait "$PYPID" || true
