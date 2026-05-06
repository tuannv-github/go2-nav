#!/bin/bash

# Get the directory where this script is located
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
PROJECT_DIR=$(cd "$SCRIPT_DIR/.." &> /dev/null && pwd)
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

# Function to check if a command is running in pane (not just shell)
pane_is_idle() {
    local pane_idx=$1
    local current_cmd=$(tmux display-message -p -t "$SESSION:0.$pane_idx" "#{pane_current_command}" 2>/dev/null)
    [[ "$current_cmd" =~ ^(zsh|bash|sh)$ ]]
}

# Function to run command if a pane is idle
run_if_idle() {
    local pane_idx=$1
    local cmd=$2
    
    if ! pane_exists "$pane_idx"; then
        echo "Pane $pane_idx does not exist. Skipping."
        return 1
    fi
    
    if ! pane_is_idle "$pane_idx"; then
        local current_cmd=$(tmux display-message -p -t "$SESSION:0.$pane_idx" "#{pane_current_command}" 2>/dev/null)
        echo "Pane $pane_idx is busy (running '$current_cmd'). Skipping."
        return 1
    fi
    
    echo "Updating Pane $pane_idx..."
    tmux send-keys -t "$SESSION:0.$pane_idx" C-c C-u
    sleep 0.2
    tmux send-keys -t "$SESSION:0.$pane_idx" "$cmd" C-m
}

# Distribute commands
# Pane 0: Joystick Controller
run_if_idle 0 "cd $PROJECT_DIR/joystick_controller && ./run_mqtt_to_ros2.sh"

# Pane 1: Realsense Video Publisher
run_if_idle 1 "cd $PROJECT_DIR && source ./setup.sh && ros2 launch realsense_video_publisher video_publisher.launch.py"

# Pane 2: Go2 Nav Realsense
run_if_idle 2 "cd $PROJECT_DIR && source ./setup.sh && ros2 launch go2_nav realsense.launch.py"

# Pane 3: Go2 Nav RTAB-Map
run_if_idle 3 "cd $PROJECT_DIR && source ./setup.sh && ros2 launch go2_nav go2_rtabmap.location.launch.py | tee go2_rtabmap.launch.py.log"

# Finalize
tmux select-pane -t $SESSION:0.0
echo "Attaching to session '$SESSION'..."
if [ -z "$TMUX" ]; then
    tmux attach-session -t $SESSION
else
    tmux switch-client -t $SESSION
fi
