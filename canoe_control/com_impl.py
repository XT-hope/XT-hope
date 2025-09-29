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
        self._app_dispatch = app_dispatch
        try:
            self._app = win32com.client.Dispatch(app_dispatch)
        except Exception as exc:  # pragma: no cover
            raise CANoeError(f"Failed to attach to CANoe COM application '{app_dispatch}': {exc}")

        try:
            self._measurement = self._app.Measurement
            self._env = self._app.Environment
            # System variable root (use 'System' and navigate Namespaces/Variables)
            self._system = self._app.System
        except Exception as exc:  # pragma: no cover
            raise CANoeError(f"Failed to acquire CANoe COM interfaces: {exc}")

    # Application lifecycle (optional)
    def start_application(self, cfg_path: str | None = None, visible: bool = True) -> None:
        try:
            # Re-dispatch in case application is not running
            self._app = win32com.client.Dispatch(self._app_dispatch)
            self._app.Visible = bool(visible)
            if cfg_path:
                self._app.Open(cfg_path)
        except Exception as exc:  # pragma: no cover
            raise CANoeError(f"Failed to start/open CANoe application: {exc}")

    def close_application(self) -> None:
        try:
            # Only attempt Quit if COM object exists
            if getattr(self, "_app", None) is not None:
                self._app.Quit()
        except Exception as exc:  # pragma: no cover
            raise CANoeError(f"Failed to close CANoe application: {exc}")

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
            var = self._resolve_system_variable(path)
            return var.Value
        except Exception as exc:
            raise CANoeError(f"Failed to read system variable '{path}': {exc}")

    def write_system_variable(self, path: str, value: Any) -> None:
        try:
            var = self._resolve_system_variable(path)
            var.Value = value
        except Exception as exc:
            raise CANoeError(f"Failed to write system variable '{path}': {exc}")

    def add_system_variable(
        self,
        path: str,
        datatype: Any,
        initial_value: Any,
        min_value: Any,
        max_value: Any,
        is_add_new_namespace: bool = True,
    ) -> None:
        """Create a system variable, optionally creating namespaces.

        The CANoe COM model is 1-based for collections. This method supports
        multi-level namespace creation or validation.
        """
        norm = path.strip()
        if not norm:
            raise CANoeError("Empty system variable path")
        norm = norm.replace("::", ".")
        parts = [p for p in norm.split(".") if p]
        if not parts:
            raise CANoeError(f"Invalid system variable path: '{path}'")
        var_name = parts[-1]
        namespaces = parts[:-1]

        try:
            node = self._system
            # Traverse or create namespaces
            for depth, ns_name in enumerate(namespaces):
                existing = None
                # search existing namespace at current level
                for i in range(1, node.Namespaces.Count + 1):
                    item = node.Namespaces.Item(i)
                    if item.Name == ns_name:
                        existing = item
                        break
                if existing is None:
                    if is_add_new_namespace:
                        node = node.Namespaces.Add(ns_name)
                    else:
                        raise CANoeError(f"Namespace '{ns_name}' does not exist")
                else:
                    node = existing

            # At this point, 'node' is the namespace that will contain the variable
            # Validate variable does not already exist
            for i in range(1, node.Variables.Count + 1):
                v = node.Variables.Item(i)
                if v.Name == var_name:
                    raise CANoeError(f"Variable '{var_name}' already exists in namespace '{'.'.join(namespaces) or '<root>'}'")

            # Create variable; set type when supported
            var = node.Variables.AddWriteableEx(var_name, initial_value, min_value, max_value)
            try:
                var.Type = datatype
            except Exception:
                # Some CANoe versions may not expose Type set; ignore if unsupported
                pass
        except Exception as exc:
            raise CANoeError(f"Failed to add system variable '{path}': {exc}")

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

    # System variable resolution
    def _resolve_system_variable(self, path: str):
        """Resolve a system variable by hierarchical path.

        Path formats supported:
          - "Ns1.Ns2.Var"
          - "Ns1::Ns2::Var"
          - "Var" (root namespace)
        """
        norm = path.strip()
        if not norm:
            raise CANoeError("Empty system variable path")
        norm = norm.replace("::", ".")
        parts = [p for p in norm.split(".") if p]
        if not parts:
            raise CANoeError(f"Invalid system variable path: '{path}'")
        var_name = parts[-1]
        namespaces = parts[:-1]

        node = self._system
        try:
            if namespaces:
                # Walk nested namespaces
                node = node.Namespaces(namespaces[0])
                for ns in namespaces[1:]:
                    node = node.Namespaces(ns)
                return node.Variables(var_name)
            else:
                # Root-level variable
                return node.Variables(var_name)
        except Exception as exc:  # pragma: no cover
            raise CANoeError(f"Failed to resolve system variable '{path}': {exc}")

