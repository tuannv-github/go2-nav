#!/usr/bin/env python3
"""
Script to save RTAB-Map occupancy grid map to a file.

This script calls the RTAB-Map get_map service and saves the occupancy grid
map to a .pgm/.yaml file pair (standard ROS map format).
"""

import sys
import argparse
import rclpy
from rclpy.node import Node
from nav_msgs.msg import OccupancyGrid
import yaml
import numpy as np
from PIL import Image
import time


class MapSaver(Node):
    def __init__(self, output_path, map_topic='/map'):
        super().__init__('map_saver')
        self.output_path = output_path
        self.map_received = False
        self.map_data = None
        
        # Subscribe to map topic
        self.subscription = self.create_subscription(
            OccupancyGrid,
            map_topic,
            self.map_callback,
            10
        )
        self.get_logger().info(f'Subscribing to map topic: {map_topic}')
    
    def map_callback(self, msg):
        """Callback when map is received from topic"""
        self.map_data = msg
        self.map_received = True
        self.get_logger().info('Map received from topic')
    
    def save_map(self):
        """Wait for map from topic and save it"""
        self.get_logger().info('Waiting for map from topic (timeout: 10 seconds)...')
        
        timeout = 10.0
        start_time = time.time()
        
        while not self.map_received and (time.time() - start_time) < timeout:
            rclpy.spin_once(self, timeout_sec=0.1)
        
        if self.map_received and self.map_data:
            return self.save_map_to_file(self.map_data)
        else:
            self.get_logger().error('Timeout waiting for map from topic!')
            self.get_logger().error('Make sure RTAB-Map is running and publishing the map.')
            return False
    
    def save_map_to_file(self, map_data):
        """Save occupancy grid map to .pgm and .yaml files"""
        if map_data.info.width == 0 or map_data.info.height == 0:
            self.get_logger().error('Map is empty!')
            return False
        
        # Prepare output filenames
        if self.output_path.endswith('.pgm'):
            pgm_path = self.output_path
            yaml_path = self.output_path.replace('.pgm', '.yaml')
        elif self.output_path.endswith('.yaml'):
            yaml_path = self.output_path
            pgm_path = self.output_path.replace('.yaml', '.pgm')
        else:
            pgm_path = f'{self.output_path}.pgm'
            yaml_path = f'{self.output_path}.yaml'
        
        try:
            # Convert occupancy grid data to image
            # Occupancy values: -1=unknown, 0-100=probability (0=free, 100=occupied)
            map_array = np.array(map_data.data, dtype=np.int8).reshape(
                (map_data.info.height, map_data.info.width)
            )
            
            # Convert to image format: 0=occupied (black), 100=free (white), 205=unknown (gray)
            image_array = np.zeros_like(map_array, dtype=np.uint8)
            image_array[map_array == -1] = 205  # Unknown
            image_array[map_array == 0] = 0     # Free (white in image, but we want black for obstacles)
            image_array[map_array == 100] = 0   # Occupied (black)
            # Actually, standard format: 0=free, 100=occupied, -1=unknown
            # For PGM: 0=black (occupied), 254=white (free), 205=gray (unknown)
            image_array = 254 - (map_array.astype(np.int16) * 254 // 100).astype(np.uint8)
            image_array[map_array == -1] = 205
            
            # Save PGM image
            image = Image.fromarray(image_array, mode='L')
            image.save(pgm_path)
            self.get_logger().info(f'Saved PGM image: {pgm_path}')
            
            # Save YAML metadata
            yaml_data = {
                'image': pgm_path.split('/')[-1],  # Just filename
                'resolution': float(map_data.info.resolution),
                'origin': [
                    float(map_data.info.origin.position.x),
                    float(map_data.info.origin.position.y),
                    float(map_data.info.origin.orientation.z)  # Yaw
                ],
                'negate': 0,
                'occupied_thresh': 0.65,
                'free_thresh': 0.196
            }
            
            with open(yaml_path, 'w') as f:
                yaml.dump(yaml_data, f, default_flow_style=False)
            
            self.get_logger().info(f'Saved YAML metadata: {yaml_path}')
            self.get_logger().info(f'Map saved successfully!')
            self.get_logger().info(f'  Resolution: {map_data.info.resolution} m/pixel')
            self.get_logger().info(f'  Size: {map_data.info.width} x {map_data.info.height} pixels')
            self.get_logger().info(f'  Origin: ({map_data.info.origin.position.x:.2f}, {map_data.info.origin.position.y:.2f})')
            
            return True
            
        except Exception as e:
            self.get_logger().error(f'Error saving map: {e}')
            import traceback
            traceback.print_exc()
            return False


def main(args=None):
    parser = argparse.ArgumentParser(description='Save RTAB-Map occupancy grid map')
    parser.add_argument(
        '--output', '-o',
        type=str,
        default='map',
        help='Output path for map files (without extension). Default: map (creates map.pgm and map.yaml)'
    )
    parser.add_argument(
        '--map-topic',
        type=str,
        default='/map',
        help='Map topic name. Default: /map'
    )
    
    args = parser.parse_args()
    
    rclpy.init(args=sys.argv)
    
    try:
        saver = MapSaver(args.output, args.map_topic)
        success = saver.save_map()
        saver.destroy_node()
        
        if success:
            sys.exit(0)
        else:
            sys.exit(1)
    except KeyboardInterrupt:
        pass
    finally:
        rclpy.shutdown()


if __name__ == '__main__':
    main()
