#!/bin/bash

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
# shellcheck source=tmux.common.sh
source "$SCRIPT_DIR/tmux.common.sh"

SESSION=remote_control
tmux_stack_begin "$SCRIPT_DIR" "$SESSION" remote "$@"
tmux_stack_max_perf "$SCRIPT_DIR"

tmux_stack_ensure_session "$SESSION" Control "$TMUX_STACK_PROJECT_DIR"
tmux_stack_ensure_four_panes "$SESSION" Control "$TMUX_STACK_PROJECT_DIR"

tmux_stack_run_pane "$SESSION" Control 0 \
    "cd $TMUX_STACK_PROJECT_DIR/3rdparties/stream/publisher && ./video-publisher.py -s /dev/video4 -d rtmp://10.1.106.210:1935/stream/go2/front"
tmux_stack_run_pane "$SESSION" Control 1 "cd $SCRIPT_DIR && ./run_go2_controller.sh"
tmux_stack_run_pane "$SESSION" Control 2 "nload usb1"

tmux select-pane -t "$SESSION:Control.3"
tmux_stack_attach "$SESSION"
