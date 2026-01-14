import os
from glob import glob
from setuptools import find_packages, setup

package_name = 'go2_front_video_viewer'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    scripts=[
        # Install Python script to lib directory for ROS2 launch compatibility
        os.path.join('go2_front_video_viewer', 'front_video_viewer_node.py'),
        os.path.join('go2_front_video_viewer', 'debug_video_node.py'),
        os.path.join('go2_front_video_viewer', 'video_bridge_node.py'),
    ],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
        # Also install to lib directory for ROS2 launch
        (os.path.join('lib', package_name), [
            os.path.join('go2_front_video_viewer', 'front_video_viewer_node.py'),
            os.path.join('go2_front_video_viewer', 'debug_video_node.py'),
            os.path.join('go2_front_video_viewer', 'video_bridge_node.py'),
        ]),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='unitree',
    maintainer_email='unitree@example.com',
    description='ROS2 package to subscribe to /frontvideostream and display using GStreamer',
    license='MIT',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'front_video_viewer = go2_front_video_viewer.front_video_viewer_node:main',
            'debug_video = go2_front_video_viewer.debug_video_node:main',
            'video_bridge = go2_front_video_viewer.video_bridge_node:main',
        ],
    },
)
