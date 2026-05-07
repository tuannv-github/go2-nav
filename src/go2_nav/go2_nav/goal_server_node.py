#!/usr/bin/env python3
"""ROS2 node that exposes a REST API for publishing `/goal_pose`."""

import math
import os
import sys
import threading
from dataclasses import dataclass
from typing import Any, Optional

import rclpy
from geometry_msgs.msg import PoseStamped
from rclpy.node import Node


def _clear_modules(prefixes: tuple[str, ...]) -> None:
    for name in list(sys.modules.keys()):
        if name.startswith(prefixes):
            del sys.modules[name]


def _load_fastapi_stack() -> tuple[Any, Any, Any, Any, Any]:
    """Import FastAPI/uvicorn with fallback for mixed pydantic environments."""
    try:
        from fastapi import Body, FastAPI
        from pydantic import BaseModel, Field
        import uvicorn

        return FastAPI, Body, uvicorn, BaseModel, Field
    except Exception as ex:
        # Common on robots: system fastapi (pydantic v1) + user-site pydantic v2.
        if "pydantic" not in str(ex).lower():
            raise

        user_site_entries = [p for p in sys.path if "/.local/lib/python" in p]
        if not user_site_entries:
            raise

        for p in user_site_entries:
            sys.path.remove(p)
        os.environ["PYTHONNOUSERSITE"] = "1"
        _clear_modules(("fastapi", "pydantic", "starlette"))

        from fastapi import Body, FastAPI
        from pydantic import BaseModel, Field
        import uvicorn

        return FastAPI, Body, uvicorn, BaseModel, Field


@dataclass
class GoalPublishResult:
    ok: bool
    message: str


class GoalServerNode(Node):
    def __init__(self) -> None:
        super().__init__("goal_server")

        self.declare_parameter("goal_topic", "/goal_pose")
        self.declare_parameter("default_frame_id", "map")
        self.declare_parameter("api_host", "0.0.0.0")
        self.declare_parameter("api_port", 8080)

        goal_topic = self.get_parameter("goal_topic").value
        self.default_frame_id = self.get_parameter("default_frame_id").value
        api_host = self.get_parameter("api_host").value
        api_port = int(self.get_parameter("api_port").value)

        self.goal_pub = self.create_publisher(PoseStamped, goal_topic, 10)

        FastAPI, Body, self._uvicorn, BaseModel, Field = _load_fastapi_stack()
        from fastapi.responses import JSONResponse

        self._json_response = JSONResponse
        self._body = Body

        class GoalRequest(BaseModel):
            x: float = Field(..., description="Goal X position in meters.")
            y: float = Field(..., description="Goal Y position in meters.")
            yaw: float = Field(0.0, description="Goal yaw in radians.")
            frame_id: str = Field("map", description="ROS frame for this goal pose.")

        self._goal_request_model = GoalRequest
        self._app = FastAPI(
            title="GO2 Goal Server",
            version="1.0.0",
            description="REST API that publishes goals to ROS topic /goal_pose.",
            openapi_tags=[
                {
                    "name": "goal",
                    "description": "Publish Nav2 goal poses to ROS topic /goal_pose.",
                }
            ],
        )
        self._setup_routes()

        self._server = self._uvicorn.Server(
            self._uvicorn.Config(
                app=self._app,
                host=api_host,
                port=api_port,
                log_level="info",
            )
        )
        self._server_thread = threading.Thread(
            target=self._server.run, daemon=True, name="goal-server-api"
        )
        self._server_thread.start()

        self.get_logger().info(f"Publishing goals to topic: {goal_topic}")
        self.get_logger().info(f"Swagger UI available at: http://{api_host}:{api_port}/docs")

    def _setup_routes(self) -> None:
        @self._app.get(
            "/health",
            tags=["goal"],
            summary="Health check",
            description="Returns API server/node health status.",
        )
        def health() -> dict:
            return {"status": "ok", "node": self.get_name()}

        @self._app.post(
            "/goal",
            tags=["goal"],
            summary="Publish goal pose",
            description="Accepts a 2D pose and publishes it to ROS topic `/goal_pose` as `geometry_msgs/PoseStamped`.",
            responses={
                200: {
                    "description": "Goal accepted and published to /goal_pose.",
                    "content": {
                        "application/json": {
                            "example": {"ok": True, "message": "Goal published to /goal_pose"}
                        }
                    },
                },
                400: {
                    "description": "Bad request payload.",
                    "content": {
                        "application/json": {
                            "example": {
                                "ok": False,
                                "message": "Missing required field: x",
                            }
                        }
                    },
                },
            },
        )
        def publish_goal(req: self._goal_request_model = self._body(..., example={
            "x": 41.87440490722656,
            "y": 12.993324279785156,
            "yaw": 1.88,
            "frame_id": "map",
        })) -> dict:
            try:
                data = req.dict() if hasattr(req, "dict") else req.model_dump()
                result = self._publish_goal(data)
                return {"ok": result.ok, "message": result.message}
            except (KeyError, TypeError, ValueError) as ex:
                return self._json_response(
                    status_code=400,
                    content={"ok": False, "message": f"Invalid payload: {ex}"},
                )

    @staticmethod
    def _yaw_to_quaternion(yaw: float) -> tuple[float, float, float, float]:
        half = 0.5 * yaw
        return 0.0, 0.0, math.sin(half), math.cos(half)

    def _publish_goal(self, req: dict) -> GoalPublishResult:
        x = float(req["x"])
        y = float(req["y"])
        yaw = float(req.get("yaw", 0.0))
        frame_id = str(req.get("frame_id", self.default_frame_id))

        goal = PoseStamped()
        goal.header.stamp = self.get_clock().now().to_msg()
        goal.header.frame_id = frame_id
        goal.pose.position.x = x
        goal.pose.position.y = y
        goal.pose.position.z = 0.0

        qx, qy, qz, qw = self._yaw_to_quaternion(yaw)
        goal.pose.orientation.x = qx
        goal.pose.orientation.y = qy
        goal.pose.orientation.z = qz
        goal.pose.orientation.w = qw

        self.goal_pub.publish(goal)
        self.get_logger().info(
            f"Published goal: x={x:.3f}, y={y:.3f}, yaw={yaw:.3f}, frame_id={goal.header.frame_id}"
        )
        return GoalPublishResult(ok=True, message="Goal published to /goal_pose")

    def stop_api_server(self) -> None:
        self._server.should_exit = True
        if self._server_thread.is_alive():
            self._server_thread.join(timeout=2.0)


def main(args: Optional[list[str]] = None) -> None:
    rclpy.init(args=args)
    node = GoalServerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.stop_api_server()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
