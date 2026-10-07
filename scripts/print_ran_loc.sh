#!/usr/bin/env bash
# Print the ran-loc mixture from /ran_loc. Highest weight is first.
# Same CycloneDDS graph as go2_controller_bridge.
# Do not use set -u around install/setup.bash.
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

set +u
# shellcheck source=/dev/null
source "${PROJECT_DIR}/install/setup.bash"
set -u

export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
export CYCLONEDDS_URI="file://${PROJECT_DIR}/cyclonedds/cyclonedds.controller.xml"

exec python3 - << 'PY'
import rclpy
from go2_controller_msgs.msg import RanLoc
from rclpy.node import Node


class PrintRanLoc(Node):
    def __init__(self):
        super().__init__('print_ran_loc')
        self.create_subscription(RanLoc, '/ran_loc', self._on_fix, 10)

    def _on_fix(self, msg):
        print(
            f'seq={msg.seq} n={len(msg.locations)} source={msg.source}',
            flush=True,
        )
        for loc in msg.locations:
            print(
                f'  x={loc.x:.2f} y={loc.y:.2f} z={loc.z:.2f} '
                f'w={loc.w:.3f} accuracy_m={loc.accuracy_m:.2f} weight={loc.weight:.2f}',
                flush=True,
            )


rclpy.init()
node = PrintRanLoc()
try:
    rclpy.spin(node)
except KeyboardInterrupt:
    pass
finally:
    node.destroy_node()
    rclpy.shutdown()
PY
