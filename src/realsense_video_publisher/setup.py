import os
from glob import glob
from setuptools import find_packages, setup

package_name = 'realsense_video_publisher'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    scripts=[
        # Install Python script to lib directory for ROS2 launch compatibility
        os.path.join('realsense_video_publisher', 'video_publisher.py'),
        os.path.join('realsense_video_publisher', 'check_image_quality.py'),
    ],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
        # Also install to lib directory for ROS2 launch
        (os.path.join('lib', package_name), [
            os.path.join('realsense_video_publisher', 'video_publisher.py'),
            os.path.join('realsense_video_publisher', 'check_image_quality.py'),
        ]),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='unitree',
    maintainer_email='unitree@example.com',
    description='ROS2 package to subscribe to realsense camera and publish video stream using GStreamer',
    license='MIT',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'video_publisher = realsense_video_publisher.video_publisher:main',
            'check_image_quality = realsense_video_publisher.check_image_quality:main',
        ],
    },
)
