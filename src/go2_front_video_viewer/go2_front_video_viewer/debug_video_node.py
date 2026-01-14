#!/usr/bin/env python3
"""
Debug Video Node

Simple node to test if Go2FrontVideoData messages are being received.
"""

import rclpy
from rclpy.node import Node
from unitree_go.msg import Go2FrontVideoData


class DebugVideo(Node):
    def __init__(self):
        super().__init__('debug_video')
        self.sub = self.create_subscription(
            Go2FrontVideoData,
            '/frontvideostream',
            self.cb,
            10
        )
        self.get_logger().info('Debug video node started, waiting for messages...')
        self.count = 0

    def cb(self, msg: Go2FrontVideoData):
        self.count += 1
        self.get_logger().info(
            f"[{self.count}] time_frame={msg.time_frame}, "
            f"len720={len(msg.video720p)}, "
            f"len360={len(msg.video360p)}, "
            f"len180={len(msg.video180p)}"
        )


def main():
    rclpy.init()
    node = DebugVideo()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
