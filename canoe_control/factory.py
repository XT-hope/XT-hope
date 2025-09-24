from __future__ import annotations

import os
from typing import Literal

from .base import CANoeController
from .com_impl import CANoeCOMController


ControllerKind = Literal["com", "dummy"]


class DummyCANoeController(CANoeController):
    """A no-op controller for testing on non-Windows/non-COM hosts.

    Methods simulate success without touching CANoe. Useful for CI or
    development when CANoe/COM is not available.
    """

    def __init__(self) -> None:
        self._running = False
        self._env = {}
        self._sys = {}

    def start_measurement(self, timeout_s: float = 10.0) -> None:
        self._running = True

    def stop_measurement(self, timeout_s: float = 10.0) -> None:
        self._running = False

    def is_measurement_running(self) -> bool:
        return self._running

    def read_system_variable(self, path: str):
        return self._sys.get(path)

    def write_system_variable(self, path: str, value):
        self._sys[path] = value

    def read_environment_variable(self, name: str):
        return self._env.get(name)

    def write_environment_variable(self, name: str, value):
        self._env[name] = value


def create_controller(kind: ControllerKind | None = None) -> CANoeController:
    """Factory for CANoe controllers.

    Selection precedence:
      1) explicit kind argument if provided
      2) env CANOE_CONTROLLER_KIND in {com,dummy}
      3) default to 'com'
    """

    resolved = kind or os.getenv("CANOE_CONTROLLER_KIND", "com").lower()
    if resolved == "com":
        return CANoeCOMController()
    if resolved == "dummy":
        return DummyCANoeController()
    raise ValueError(f"Unknown controller kind: {resolved}")

