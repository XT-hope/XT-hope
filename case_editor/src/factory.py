from __future__ import annotations

import os
from typing import Literal

from base import CANoeController, CANoeError
from com_impl import CANoeCOMController
from typing import Any

try:
    import win32com.client  # type: ignore
except Exception as e:  # pragma: no cover
    win32com = None  # type: ignore


ControllerKind = Literal["default-com", "defind-com"]

# 测试运行，切换到Automation目录，执行：python.exe -m canoe_control.factory


class UserDefinedCANoeController(CANoeController):
    """A no-op controller for testing on non-Windows/non-COM hosts.

    Methods simulate success without touching CANoe. Useful for CI or
    development when CANoe/COM is not available.
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
            # System variable root (use 'System' and navigate Namespaces/Variables)
            self._system = self._app.System
            self._bus = self._app.bus
        except Exception as exc:  # pragma: no cover
            raise CANoeError(f"Failed to acquire CANoe COM interfaces: {exc}")

    def start_measurement(self, timeout_s: float = 10.0) -> None:
        pass

    def stop_measurement(self, timeout_s: float = 10.0) -> None:
        pass

    def is_measurement_running(self) -> bool:
        pass

    def read_system_variable(self, path: str):
        pass

    def write_system_variable(self, path: str, value):
        pass
        
    def add_system_variable(self, path: str, value):
        pass

    def read_environment_variable(self, name: str):
        pass
    def write_environment_variable(self, name: str, value: Any):
        pass
    
    def read_signal(self, path):
        pass
    
    def start_logging(self, savePath):  
        pass
    
    def stop_logging(self):
        pass
    
    def open_cfg(self, cfg_path):
        pass

def create_controller(kind: ControllerKind | None = None) -> CANoeController:
    """Factory for CANoe controllers.

    Selection precedence:
      1) explicit kind argument if provided
      2) env CANOE_CONTROLLER_KIND in {com,dummy}
      3) default to 'default-com'
    """

    resolved = kind or os.getenv("CANOE_CONTROLLER_KIND", "default-com").lower()
    if resolved == "default-com":
        return CANoeCOMController()
    if resolved == "defind-com":
        return UserDefinedCANoeController()
    raise CANoeError(f"Unknown controller kind: {resolved}")


if __name__=="__main__":
    import time
    c = create_controller()
    c.start_measurement()
    time.sleep(1)
    c.write_system_variable("simulink::Scenelect", 10)

    c.write_environment_variable("E_Control_MIRM_MIRM_0x4D2_Stre_Interior_Rear_Mirror_OpenState_S_Rv",2)
    # items=[("E_Control_MIRM_MIRM_0x4D2_Stre_Int_Rearview_Mirror_Cur_Brightness_S_Rv",2),("E_Control_VDS_ADC_0x712_ADC_Diag_712_S_Rv",10)]
    # c.write_environment_variables(items)
    time.sleep(5)
    print(c.read_system_variable("DriverAction::gear"))
    print(c.read_system_variable("simulink::SceneSelect"))
    print(c.read_environment_variable("E_Control_MIRM_MIRM_0x4D2_Stre_Interior_Rear_Mirror_OpenState_S_Rv"))
    print(c.read_signal("CAN 1::VCU_0x4BE::Act_drv_mod"))
    
    c.write_system_variable("DriverAction::driverspeed", 300)
    time.sleep(3)
    print(c.read_system_variable("DriverAction::driverspeed"))
    #c.add_system_variable("MyNS::name", "xiongtao", isAddNewNamespace=False)
    #c.add_system_variable("MyNS4::age", 18, isAddNewNamespace=True)
    c.stop_measurement()
    #c.open_cfg("D:\\MyProgramm\\sim_modelbed-master\\sim_modelbed-master\\_prj_PlatformC_J6M_SC2E_HIL\\_prj_SC2E_caone_hil\\SC2E.cfg")
