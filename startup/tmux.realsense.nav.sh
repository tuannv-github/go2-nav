#!/bin/bash

# Get the directory where this script is located
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
PROJECT_DIR=$(cd "$SCRIPT_DIR/.." &> /dev/null && pwd)

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
run_pane_cmd 3 "cd $PROJECT_DIR && source ./setup.sh && ros2 launch go2_nav go2_rtabmap.location.launch.py"

# Separate window (tab): Nav2 stack
if tmux list-windows -t $SESSION -F '#{window_name}' | grep -q '^nav$'; then
    tmux kill-window -t $SESSION:nav
fi
tmux new-window -t $SESSION -n nav -c "$PROJECT_DIR"
tmux send-keys -t "$SESSION:nav" "cd $PROJECT_DIR && source ./setup.sh && ros2 launch go2_nav go2_nav2.launch.py" C-m

# Finalize
tmux select-pane -t $SESSION:0.0
echo "Attaching to session '$SESSION'..."
if [ -z "$TMUX" ]; then
    tmux attach-session -t $SESSION
else
    tmux switch-client -t $SESSION
fi
