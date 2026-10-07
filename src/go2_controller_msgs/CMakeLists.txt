cmake_minimum_required(VERSION 3.5)
project(go2_controller_msgs)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/RanFix.msg"
  "msg/RanLoc.msg"
  DEPENDENCIES std_msgs
)

ament_package()
