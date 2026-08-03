import rclpy
from rclpy.node import Node
from tf2_ros import TransformException
from tf2_ros.buffer import Buffer
from tf2_ros.transform_listener import TransformListener
import requests
import json

class LocationPublisher(Node):
    def __init__(self):
        super().__init__('location_publisher_node')
        
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        
        self.declare_parameter('server_url', 'http://10.1.101.216:8081/api/demo/ue-location')
        self.declare_parameter('supi', 'imsi-001010000000009')
        self.declare_parameter('enabled', True)
        self.declare_parameter('timeout_sec', 0.5)

        self.url = self.get_parameter('server_url').get_parameter_value().string_value
        self.supi = self.get_parameter('supi').get_parameter_value().string_value
        self.enabled = self.get_parameter('enabled').get_parameter_value().bool_value
        self.timeout_sec = self.get_parameter('timeout_sec').get_parameter_value().double_value

        # Timer to publish every 1 second
        self.timer = self.create_timer(1.0, self.timer_callback)
        self.get_logger().info(f'Location Publisher Node started. Target: {self.url} (enabled={self.enabled})')

    def timer_callback(self):
        if not self.enabled:
            return

        try:
            # Look up transform from map to base_link
            # We want the position of base_link in map frame
            now = rclpy.time.Time()
            trans = self.tf_buffer.lookup_transform(
                'map',
                'base_link',
                now)
            
            x = trans.transform.translation.x
            y = trans.transform.translation.y
            z = trans.transform.translation.z
            
            payload = {
                "supi": self.supi,
                "x": x,
                "y": y
                # "z": z
            }

            headers = {
                'accept': 'application/json',
                'Content-Type': 'application/json'
            }
            
            try:
                response = requests.post(self.url, headers=headers, data=json.dumps(payload), timeout=self.timeout_sec)
                if response.status_code in (200, 201):
                    self.get_logger().info(f'Successfully published: x={x:.2f}, y={y:.2f}, z={z:.2f}', throttle_duration_sec=5.0)
                else:
                    self.get_logger().warning(f'Failed to publish. Status: {response.status_code}, Body: {response.text}', throttle_duration_sec=5.0)
            except requests.exceptions.RequestException as e:
                self.get_logger().warn(f'Location server unreachable ({self.url}): {e}', throttle_duration_sec=10.0)
                
        except TransformException as ex:
            self.get_logger().info(
                f'Could not transform map to base_link: {ex}')

def main(args=None):
    rclpy.init(args=args)
    node = LocationPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
