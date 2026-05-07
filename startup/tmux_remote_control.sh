#!/bin/bash

# Get script and project directories
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
PROJECT_DIR=$(cd "$SCRIPT_DIR/.." &> /dev/null && pwd)

echo "Setting Jetson to max performance..."
if ! bash "$SCRIPT_DIR/cpu.sh"; then
    echo "Warning: failed to apply max performance settings, continuing startup."
fi

SESSION_NAME="remote_control"

# Check if session exists
if ! tmux has-session -t $SESSION_NAME 2>/dev/null; then
    echo "Creating new session $SESSION_NAME"
    tmux new-session -d -s $SESSION_NAME -n "Control" -c "$PROJECT_DIR"
    # Pane 0: Video Publisher
    tmux send-keys -t $SESSION_NAME:0.0 "cd $PROJECT_DIR/3rdparties/stream/publisher && ./video-publisher.py -s 10.1.106.210" C-m
else
    echo "Session $SESSION_NAME already exists, verifying panes..."
fi

# Pane 1: Joystick Controller (Split bottom)
if ! tmux list-panes -t $SESSION_NAME:0 | grep -q "^1:"; then
    tmux split-window -v -t $SESSION_NAME:0.0 -c "$PROJECT_DIR"
    tmux send-keys -t $SESSION_NAME:0.1 "cd $SCRIPT_DIR && ./run_go2_controller.sh" C-m
fi

# Pane 2: nload monitor (Vertical split of Pane 1)
if ! tmux list-panes -t $SESSION_NAME:0 | grep -q "^2:"; then
    tmux split-window -h -t $SESSION_NAME:0.1 -c "$PROJECT_DIR"
    tmux send-keys -t $SESSION_NAME:0.2 "nload usb1" C-m
fi

# Pane 3: User Command (Vertical split of Pane 0)
if ! tmux list-panes -t $SESSION_NAME:0 | grep -q "^3:"; then
    tmux split-window -h -t $SESSION_NAME:0.0 -c "$PROJECT_DIR"
fi

# Select the user command pane (Pane 3) as active
tmux select-pane -t $SESSION_NAME:0.3

# Attach to the session
if [ -z "$TMUX" ]; then
    tmux attach-session -t $SESSION_NAME
else
    tmux switch-client -t $SESSION_NAME
fi
