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
        
        self.url = 'http://10.1.101.216:8086/api/demo/ue-location'
        self.supi = 'imsi-001010000000009'
        
        # Timer to publish every 1 second
        self.timer = self.create_timer(1.0, self.timer_callback)
        self.get_logger().info(f'Location Publisher Node started. Target: {self.url}')

    def timer_callback(self):
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
                response = requests.post(self.url, headers=headers, data=json.dumps(payload), timeout=0.5)
                if response.status_code == 200 or response.status_code == 201:
                    self.get_logger().info(f'Successfully published: x={x:.2f}, y={y:.2f}, z={z:.2f}')
                else:
                    self.get_logger().warning(f'Failed to publish. Status: {response.status_code}, Body: {response.text}')
            except requests.exceptions.RequestException as e:
                self.get_logger().error(f'HTTP Request failed: {e}')
                
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
