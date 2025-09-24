from __future__ import annotations

import time
from typing import Any

try:
    import win32com.client  # type: ignore
except Exception as e:  # pragma: no cover
    win32com = None  # type: ignore

from .base import CANoeController, CANoeError


class CANoeCOMController(CANoeController):
    """COM-based CANoe controller.

    Attaches to an already-running CANoe instance via COM and provides
    minimal operations required by tests.
    """

    def __init__(self, app_dispatch: str = "CANoe.Application") -> None:
        if win32com is None:
            raise CANoeError("pywin32 is required to use CANoe COM controller (win32com.client not available)")
        try:
            self._app = win32com.client.Dispatch(app_dispatch)
        except Exception as exc:  # pragma: no cover
            raise CANoeError(f"Failed to attach to CANoe COM application '{app_dispatch}': {exc}")

        try:
            self._measurement = self._app.Measurement
            self._env = self._app.Environment
            self._sysvar = self._app.SystemVariables
        except Exception as exc:  # pragma: no cover
            raise CANoeError(f"Failed to acquire CANoe COM interfaces: {exc}")

    # Measurement
    def start_measurement(self, timeout_s: float = 10.0) -> None:
        if self.is_measurement_running():
            return
        self._measurement.Start()
        self._wait(lambda: self.is_measurement_running(), timeout_s, "start measurement")

    def stop_measurement(self, timeout_s: float = 10.0) -> None:
        if not self.is_measurement_running():
            return
        self._measurement.Stop()
        self._wait(lambda: not self.is_measurement_running(), timeout_s, "stop measurement")

    def is_measurement_running(self) -> bool:
        try:
            return bool(self._measurement.Running)
        except Exception as exc:  # pragma: no cover
            raise CANoeError(f"Failed to query measurement state: {exc}")

    # Environment variables
    def read_environment_variable(self, name: str) -> Any:
        try:
            return self._env.GetVariable(name).Value
        except Exception as exc:
            raise CANoeError(f"Failed to read environment variable '{name}': {exc}")

    def write_environment_variable(self, name: str, value: Any) -> None:
        try:
            var = self._env.GetVariable(name)
            var.Value = value
        except Exception as exc:
            raise CANoeError(f"Failed to write environment variable '{name}': {exc}")

    # System variables
    def read_system_variable(self, path: str) -> Any:
        try:
            return self._sysvar(path).Value
        except Exception as exc:
            raise CANoeError(f"Failed to read system variable '{path}': {exc}")

    def write_system_variable(self, path: str, value: Any) -> None:
        try:
            self._sysvar(path).Value = value
        except Exception as exc:
            raise CANoeError(f"Failed to write system variable '{path}': {exc}")

    # Helpers
    @staticmethod
    def _now() -> float:
        return time.monotonic()

    def _wait(self, cond, timeout_s: float, what: str) -> None:
        deadline = self._now() + max(timeout_s, 0.0)
        while self._now() < deadline:
            try:
                if cond():
                    return
            except Exception as exc:  # pragma: no cover
                raise CANoeError(f"Error while waiting to {what}: {exc}")
            time.sleep(0.02)
        raise CANoeError(f"Timeout while waiting to {what} (timeout={timeout_s}s)")

