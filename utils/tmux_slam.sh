#!/bin/bash

# Get the directory where this script is located
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
PROJECT_DIR=$(cd "$SCRIPT_DIR/.." &> /dev/null && pwd)
SESSION="go2nav"

# Check if session exists
if ! tmux has-session -t $SESSION 2>/dev/null; then
    echo "Creating new session $SESSION"
    tmux new-session -d -s $SESSION -n main -c "$PROJECT_DIR"
    # Pane 0: Joystick Controller
    tmux send-keys -t $SESSION:0.0 "cd $PROJECT_DIR/joystick_controller && ./run_mqtt_to_ros2.sh" C-m
else
    echo "Session $SESSION already exists, verifying panes..."
fi

# Pane 1: Split vertically from 0 (creates bottom row)
if ! tmux list-panes -t $SESSION:0 | grep -q "^1:"; then
    tmux split-window -v -p 50 -t $SESSION:0.0 -c "$PROJECT_DIR"
    # We'll set this pane up later (it will become Pane 1 or 2 depending on subsequent splits)
fi

# Pane 2: Split top row horizontally
if ! tmux list-panes -t $SESSION:0 | grep -q "^2:"; then
    tmux split-window -h -p 50 -t $SESSION:0.0 -c "$PROJECT_DIR"
    # Top-Right: realsense_video_publisher
    tmux send-keys -t $SESSION:0.2 "cd $PROJECT_DIR && source ./setup.sh && ros2 launch realsense_video_publisher video_publisher.launch.py" C-m
fi

# Pane 3: Split bottom row horizontally
if ! tmux list-panes -t $SESSION:0 | grep -q "^3:"; then
    # Note: Pane 1 is the bottom-left pane
    tmux split-window -h -p 50 -t $SESSION:0.1 -c "$PROJECT_DIR"
    
    # Bottom-Left: go2_nav realsense (Pane 1)
    tmux send-keys -t $SESSION:0.1 "cd $PROJECT_DIR && source ./setup.sh && ros2 launch go2_nav realsense.launch.py" C-m
    
    # Bottom-Right: go2_nav rtabmap (Pane 3)
    tmux send-keys -t $SESSION:0.3 "cd $PROJECT_DIR && source ./setup.sh && ros2 launch go2_nav go2_rtabmap.launch.py | tee go2_rtabmap.launch.py.log" C-m
fi

# Set tiled layout for even 2x2 distribution
tmux select-layout -t $SESSION:0 tiled

# Select the first pane and attach
tmux select-pane -t $SESSION:0.0
echo "Attaching to tmux session '$SESSION'"

if [ -z "$TMUX" ]; then
    tmux attach-session -t $SESSION
else
    tmux switch-client -t $SESSION
fi
