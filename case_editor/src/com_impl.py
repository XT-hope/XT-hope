from __future__ import annotations

import time
from typing import Any
import pythoncom
from datetime import datetime
import os
from pathlib import Path

try:
    import win32com.client  # type: ignore
except Exception as e:  # pragma: no cover
    win32com = None  # type: ignore

from base import CANoeController, CANoeError

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
            self._system = self._app.System
            self._bus = self._app.bus
            self._os=self._app.Configuration.OnlineSetup
        except Exception as exc:  # pragma: no cover
            raise CANoeError(f"Failed to acquire CANoe COM interfaces: {exc}")

    # Measurement
    def start_measurement(self, timeout_s: float = 10.0) -> None:
        if self.is_measurement_running():
            print("CANoe: Measurement already running")
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
            env = self._env.GetVariable(name)
            env.Value = value
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
        
    def add_system_variable(self, path: str, initialValue, minValue=pythoncom.Empty, maxValue=pythoncom.Empty, isAddNewNamespace: bool=True) -> None:
        """
        initialValue: canoe会根据初始值类型创建对应类型的变量
        canoe中变量的类型:
           - Integer
           - Float
           - String
           - Float Array
           - Integer Array
           - Long Long
           - Byte Array
           - Generic Array
           - Struct
           - Invalid
        """
        norm = path.strip()
        if not norm:
            raise CANoeError("Empty system variable path")
        norm = norm.replace("::", ".")
        parts = [p for p in norm.split(".") if p]
        if not parts:
            raise CANoeError(f"Invalid system variable path: '{path}'")
        var_name = parts[-1]
        namespaces = "::".join(parts[:-1])
        try:
            ns = self._system.Namespaces(namespaces)
        except Exception as e:
            ns = None
        if isAddNewNamespace:
            if ns is None:  # Namespace does not exist, create it
                ns = self._system.Namespaces.Add(namespaces)
                ns.Variables.AddWriteableEx(var_name, initialValue, minValue, maxValue)
                return
            raise CANoeError(f"Namespace '{namespaces}' already exists")
        else:
            if ns is not None:  # Namespace exists, add variable to it
                try:
                    var=ns.Variables(var_name)
                except Exception as e:
                    var = None
                if var is None:  # Variable does not exist, add it to the namespace
                    ns.Variables.AddWriteableEx(var_name, initialValue, minValue, maxValue)
                    return
                raise CANoeError(f"Variable '{var_name}' already exists in namespace '{namespaces}'")
            raise CANoeError(f"Namespace '{namespaces}' does not exist")

    def read_signal(self, path: str):
        """
        path: "channel::message::signal"
        """
        if 'CAN 1' in path:
            norm = path.strip().replace('CAN 1', '1').split("::")
        elif 'CAN 2' in path:
            norm = path.strip().replace('CAN 2', '2').split("::")
        channel=norm[0]
        message=norm[1]
        signal=norm[2]
        if len(norm) != 3:
            raise CANoeError(f"Invalid signal path: '{path}'")
        try:
            sig=self._bus.GetSignal(channel, message, signal)
            sig_value=sig.Value
            return sig_value
        except Exception as e:
            raise CANoeError(f"Failed to read signal '{path}': {e}") from e
    
    def start_logging(self, base_dir, case_id, logPath):
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        try:
            Path(base_dir).parent.mkdir(parents=True, exist_ok=True)
            blf_path=os.path.join(base_dir,(f"{case_id}_{run_id}.blf"))
            print(f"CANoe: Start logging to '{blf_path}' for test case {case_id}")
            self._os.LoggingCollection.Item(1).FullName=blf_path
        except Exception as e:
            raise CANoeError(f"Failed to set trace logging path '{logPath}': {e}")
        try:
            self._os.LoggingCollection.Item(1).Trigger.Start()
        except Exception as e:
            raise CANoeError(f"Failed to start trace logging: {e}")
        return blf_path
        
    def stop_logging(self):
        try:
            self._os.LoggingCollection.Item(1).Trigger.Stop()
        except Exception as e:
            raise CANoeError(f"Failed to stop trace logging: {e}")

    @staticmethod
    def _now() -> float:
        return time.monotonic()

    def _wait(self, cond, timeout_s: float, what: str) -> None:
        deadline = self._now() + max(timeout_s, 0.0)
        while self._now() < deadline:
            try:
                if cond():
                    print(f"CANoe: {what}")
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
        if not parts or len(parts) < 2:
            raise CANoeError(f"Invalid system variable path: '{path}'")
        var_name = parts[-1]
        namespaces = "::".join(parts[:-1])

        try:
            ns = self._system.Namespaces(namespaces)
        except Exception as exc:
            raise CANoeError(f"Namespace '{namespaces}' does not exist") from exc
        
        try:
            var = ns.Variables(var_name)
            return var
        except Exception as exc:
            raise CANoeError(f"Variable '{var_name}' does not exist in namespace '{namespaces}'")
        
    def creat_panels(self,nums):
        pass
    
    def add_panel(self,panel_name):
        pass
    
    def remove_panel(self,panel_name):
        pass
    
    def get_panel_by_name(self,panel_name):
        pass
    
    def get_panel_by_index(self,panel_idx):
        pass
    
    def set_panel(self,panel_name=None,panel_idx=None,**panel_props):
        if panel_name is not None:
            panel=self.get_panel_by_name(panel_name)
        elif panel_idx is not None:
            panel=self.get_panel_by_index(panel_idx)
        pass

    def open_cfg(self, cfg_path):
        try:
            self._app.Open(cfg_path)
            print(f"CANoe: Opened configuration file '{cfg_path}'")
        except Exception as e:
            raise CANoeError(f"Failed to open configuration file '{cfg_path}': {e}")
