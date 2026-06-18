#!/bin/bash

# Get the directory where this script is located
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
PROJECT_DIR=$(cd "$SCRIPT_DIR/.." &> /dev/null && pwd)
# VLAA voice/LLM client (default: ~/vlaa/app_robots); override before running script if installed elsewhere.
VLAA_APP_ROBOTS="${VLAA_APP_ROBOTS:-$HOME/vlaa/app_robots}"

echo "Setting Jetson to max performance..."
if ! bash "$SCRIPT_DIR/cpu.sh"; then
    echo "Warning: failed to apply max performance settings, continuing startup."
fi

SESSION="go2nav"

# Check if session exists, create if not
if ! tmux has-session -t $SESSION 2>/dev/null; then
    echo "Creating new session $SESSION"
    tmux new-session -d -s $SESSION -n main -c "$PROJECT_DIR"
fi

# Ensure we have exactly 4 panes in a standard layout
PANE_COUNT=$(tmux list-panes -t $SESSION:0 | wc -l)
if [ "$PANE_COUNT" -ne 4 ]; then
    echo "Adjusting panes to reach 4..."
    # If we have too many, it's hard to manage, but if too few, we split
    while [ $(tmux list-panes -t $SESSION:0 | wc -l) -lt 4 ]; do
        tmux split-window -t $SESSION:0.0 -c "$PROJECT_DIR"
    done
fi

# Set tiled layout to enforce Z-order (0:TL, 1:TR, 2:BL, 3:BR)
tmux select-layout -t $SESSION:0 tiled
sleep 1 # Wait for layout to settle and shell prompts to appear

# Function to check if pane exists and is alive
pane_exists() {
    local pane_idx=$1
    tmux list-panes -t "$SESSION:0" -F '#{pane_index}' 2>/dev/null | grep -q "^${pane_idx}$"
}

# Stop prior jobs from this stack: SIGINT foreground in each pane, then targeted pkill.
# Bracket tricks in pkill patterns avoid matching the pkill command line itself.
kill_previous_children() {
    echo "Stopping previous stack jobs..."
    local pane_idx
    for pane_idx in 0 1 2 3; do
        if pane_exists "$pane_idx"; then
            tmux send-keys -t "$SESSION:0.$pane_idx" C-c
            sleep 0.4
            tmux send-keys -t "$SESSION:0.$pane_idx" C-c
        fi
    done
    sleep 1

    pkill -f '[r]un_mqtt_to_ros2\.sh' 2>/dev/null || true
    pkill -f '[r]un_go2_controller\.sh' 2>/dev/null || true
    pkill -f '[r]os2 launch go2_controller go2_controller\.launch\.py' 2>/dev/null || true
    pkill -f '[r]os2 launch realsense_video_publisher video_publisher\.launch\.py' 2>/dev/null || true
    pkill -f '[r]os2 launch go2_nav realsense\.launch\.py' 2>/dev/null || true
    pkill -f '[r]os2 launch go2_nav go2_rtabmap\.location\.launch\.py' 2>/dev/null || true
    pkill -f '[r]os2 launch go2_nav go2_nav2\.launch\.py' 2>/dev/null || true
    pkill -f '[r]os2 launch go2_nav livox_mid360\.launch\.py' 2>/dev/null || true
    pkill -f '[a]pp_robots/main\.py' 2>/dev/null || true
    pkill -f '[p]ython3 main\.py --robot-model' 2>/dev/null || true
    pkill -f '[r]un_vlaa\.sh' 2>/dev/null || true
    pkill -f '[a]udio_recorder' 2>/dev/null || true
    pkill -f '[a]udio_speaker' 2>/dev/null || true
    pkill -f '[w]ifi-heartbeat\.sh' 2>/dev/null || true

    # Safety net for Option 1 (dynamic Pulse handoff): if a previous run_vlaa.sh
    # was killed before its EXIT trap could resume Pulse cards, restore them now
    # so PulseAudio sees the Blink mic / USB speaker again when VLAA is not running.
    if command -v pactl >/dev/null 2>&1; then
        pactl list short cards 2>/dev/null \
            | awk '$2 ~ /Blink500B2|10d6_4803|USB_Composite|0909_005b/ {print $2}' \
            | xargs -r -I{} pactl suspend-card {} 0 2>/dev/null || true
    fi

    sleep 0.5
}

kill_previous_children

# Run command in pane (cleanup already ran above)
run_pane_cmd() {
    local pane_idx=$1
    local cmd=$2

    if ! pane_exists "$pane_idx"; then
        echo "Pane $pane_idx does not exist. Skipping."
        return 1
    fi

    echo "Starting pane $pane_idx..."
    tmux send-keys -t "$SESSION:0.$pane_idx" C-c C-u
    sleep 0.2
    tmux send-keys -t "$SESSION:0.$pane_idx" "$cmd" C-m
}

# Distribute commands
# Pane 0: startup/run_go2_controller.sh — MQTT + Nav /cmd_vel → /wirelesscontroller (cyclonedds.go2.xml)
run_pane_cmd 0 "cd $SCRIPT_DIR && ./run_go2_controller.sh"

# Pane 1: Realsense Video Publisher
run_pane_cmd 1 "cd $PROJECT_DIR && source ./setup.sh && ros2 launch realsense_video_publisher video_publisher.launch.py"

# Pane 2: Go2 Nav Realsense
run_pane_cmd 2 "cd $PROJECT_DIR && source ./setup.sh && export CYCLONEDDS_URI=file://$PROJECT_DIR/cyclonedds.realsense.xml && ros2 launch go2_nav realsense.launch.py"

# Pane 3: Go2 Nav RTAB-Map
run_pane_cmd 3 "cd $PROJECT_DIR && source ./setup.sh && ros2 launch go2_nav go2_rtabmap.livox.location.launch.py"

# Separate window (tab): Livox MID-360 driver (pane 0) + Nav2 stack (pane 1)
if tmux list-windows -t $SESSION -F '#{window_name}' | grep -q '^nav$'; then
    tmux kill-window -t $SESSION:nav
fi
tmux new-window -t $SESSION -n nav -c "$PROJECT_DIR"
tmux send-keys -t "$SESSION:nav.0" "cd $PROJECT_DIR && source ./setup.sh && ros2 launch go2_nav livox_mid360.launch.py" C-m
tmux split-window -v -t "$SESSION:nav.0" -c "$PROJECT_DIR"
tmux send-keys -t "$SESSION:nav.1" "cd $PROJECT_DIR && source ./setup.sh && ros2 launch go2_nav go2_nav2.launch.py" C-m
tmux select-layout -t "$SESSION:nav" even-vertical

# Window (tab): VLAA voice/LLM client (Go2)
if tmux list-windows -t $SESSION -F '#{window_name}' | grep -q '^llm$'; then
    tmux kill-window -t $SESSION:llm
fi
tmux new-window -t $SESSION -n llm -c "$VLAA_APP_ROBOTS"
# Launch VLAA via run_vlaa.sh, which:
#   1. waits for the Blink500B2+ mic (wait_for_blink500b2.sh),
#   2. asks PulseAudio to suspend the Blink + USB Composite cards so PortAudio/
#      PyAudio can open them via the ALSA hostapi for the lifetime of VLAA,
#   3. runs `python3 main.py --robot-model go2`,
#   4. resumes those Pulse cards on exit so the rest of the system can use them.
# This is the dynamic counterpart to the (old) udev PULSE_IGNORE rules, see fix_audio.md.
tmux send-keys -t "$SESSION:llm.0" "VLAA_APP_ROBOTS=\"$VLAA_APP_ROBOTS\" bash \"$SCRIPT_DIR/run_vlaa.sh\"" C-m

# Window (tab): WiFi heartbeat monitor
if tmux list-windows -t $SESSION -F '#{window_name}' | grep -q '^wifi$'; then
    tmux kill-window -t $SESSION:wifi
fi
tmux new-window -t $SESSION -n wifi -c "$SCRIPT_DIR"
tmux send-keys -t "$SESSION:wifi.0" "bash \"$SCRIPT_DIR/wifi-heartbeat.sh\"" C-m

# Finalize
tmux select-pane -t $SESSION:0.0
echo "Attaching to session '$SESSION'..."
if [ -z "$TMUX" ]; then
    tmux attach-session -t $SESSION
else
    tmux switch-client -t $SESSION
fi
