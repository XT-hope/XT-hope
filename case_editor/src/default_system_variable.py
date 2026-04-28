from dataclasses import dataclass
from typing import Any, Dict, Optional, Set, Union
from error_manager import CANoeError

Number = Union[int, float]

@dataclass(frozen=True)
class VarSchema:
    path: str
    datatype: str                   # 'int'|'float'|'bool'|'str'
    min: Optional[Number] = None
    max: Optional[Number] = None
    allowed: Optional[Set[Any]] = None
    Unit: str = ""
    initValue: Optional[Number] = None

class Simulink:
    Ego_PosX   = VarSchema("simulink::Ego_PosX",   datatype="float", Unit="m", initValue=0.0)
    Ego_PosY   = VarSchema("simulink::Ego_PosY",   datatype="float", Unit="m", initValue=0.0)
    Ego_YawAngle = VarSchema("simulink::Ego_YawAngle", datatype="float", min=-180, max=180, Unit="deg", initValue=0.0)
    obj_dist_lon = VarSchema("simulink::obj_dist_lon", datatype="float", Unit="m")
    obj_dist_lat = VarSchema("simulink::obj_dist_lat", datatype="float", Unit="m")
    obj_spd_rel  = VarSchema("simulink::obj_spd_rel",  datatype="float", Unit="m/s")
    SceneReset   = VarSchema("simulink::SceneReset",   datatype="int", min=0, max=2, initValue=2)
    SceneSelect  = VarSchema("simulink::SceneSelect",  datatype="int", initValue=1)
    dynamic_disconnect = VarSchema("simulink::dynamic_disconnect",  datatype="int", initValue=0, min=0, max=1)

class DriverAction:
    accelpedal: VarSchema = VarSchema("DriverAction::accelpedal", datatype="int", min=0, max=100, Unit="Pedal position", initValue=0)
    brakepedal: VarSchema = VarSchema("DriverAction::brakepedal", datatype="int", min=0, max=100, Unit="Pedal position", initValue=0)
    driverspeed: VarSchema = VarSchema("DriverAction::driverspeed", datatype="int", min=0, max=200, Unit="Target speed of the driver", initValue=0)
    gear: VarSchema = VarSchema("DriverAction::gear", datatype="int", min=0, max=4, Unit="Current gear", initValue=4)
    Reset_Speed: VarSchema = VarSchema("DriverAction::Reset_Speed", datatype="int", min=0, max=1, Unit="Reset speed", initValue=1)
    steerwheelang: VarSchema = VarSchema("DriverAction::steerwheelang", datatype="float", min=-720, max=720, Unit="Steering wheel angle", initValue=0.0)
    steertorque: VarSchema = VarSchema("DriverAction::steertorque", datatype="float", min=-20, max=20, Unit="Steering torque", initValue=0.1)
    turnlight: VarSchema = VarSchema("DriverAction::turnlight", datatype="int", Unit="Turn light", min=-2, max=2, initValue=0)

class FunctionSwitch:
    ACC_DistDown: VarSchema = VarSchema("FunctionSwitch::ACC_DistDown", datatype="int", min=0, max=1, Unit="ACC distance down", initValue=0)
    ACC_DistUp: VarSchema = VarSchema("FunctionSwitch::ACC_DistUp", datatype="int", min=0, max=1, Unit="ACC distance up", initValue=0)
    ACC_ON: VarSchema = VarSchema("FunctionSwitch::ACC_ON", datatype="int", min=0, max=1, Unit="ACC on", initValue=1)
    ACC_Resume: VarSchema = VarSchema("FunctionSwitch::ACC_Resume", datatype="int", min=0, max=1, Unit="ACC resume", initValue=0)
    ACC_Set: VarSchema = VarSchema("FunctionSwitch::ACC_Set", datatype="int", min=0, max=1, Unit="ACC set", initValue=0)
    ACC_SpeedLimit: VarSchema = VarSchema("FunctionSwitch::ACC_SpeedLimit", datatype="int", min=0, max=1, Unit="ACC speed limit", initValue=0)
    ACC_Switch: VarSchema = VarSchema("FunctionSwitch::ACC_Switch", datatype="int", min=0, max=1, Unit="ACC switch", initValue=0)
    AEB_Enable: VarSchema = VarSchema("FunctionSwitch::AEB_Enable", datatype="int", min=0, max=1, Unit="AEB enable", initValue=1)
    BrakeNoExitADCEnable: VarSchema = VarSchema("FunctionSwitch::BrakeNoExitADCEnable", datatype="int", min=0, max=1, Unit="Brake no exit ADC enable", initValue=0)
    CNOA_ON: VarSchema = VarSchema("FunctionSwitch::CNOA_ON", datatype="int", min=0, max=1, Unit="CNOA on", initValue=0)
    Dipilot_Switch: VarSchema = VarSchema("FunctionSwitch::Dipilot_Switch", datatype="int", min=0, max=1, Unit="Dipilot switch", initValue=0)
    HNOA_ON: VarSchema = VarSchema("FunctionSwitch::HNOA_ON", datatype="int", min=0, max=1, Unit="HNOA on", initValue=0)
    LCC_ON: VarSchema = VarSchema("FunctionSwitch::LCC_ON", datatype="int", min=0, max=1, Unit="LCC on", initValue=0)
    LDP_ON: VarSchema = VarSchema("FunctionSwitch::LDP_ON", datatype="int", min=0, max=1, Unit="LDP on", initValue=0)
    LDW_ON: VarSchema = VarSchema("FunctionSwitch::LDW_ON", datatype="int", min=0, max=1, Unit="LDW on", initValue=1)
    Left_Paddle: VarSchema = VarSchema("FunctionSwitch::Left_Paddle", datatype="int", min=0, max=1, Unit="Left Paddle", initValue=0)
    Left_Paddle_Long: VarSchema = VarSchema("FunctionSwitch::Left_Paddle_Long", datatype="int", min=0, max=1, Unit="Left Paddle Long", initValue=0)
    PCW_Level: VarSchema = VarSchema("FunctionSwitch::PCW_Level", datatype="int", min=0, max=4, Unit="PCW Level", initValue=3)
    Right_Paddle: VarSchema = VarSchema("FunctionSwitch::Right_Paddle", datatype="int", min=0, max=1, Unit="Right Paddle", initValue=0)
    Right_Paddle_Long: VarSchema = VarSchema("FunctionSwitch::Right_Paddle_Long", datatype="int", min=0, max=1, Unit="Right Paddle Long", initValue=0)
    CSW_Enable_S: VarSchema = VarSchema("FunctionSwitch::CSW_Enable_S", datatype="int", min=0, max=3, Unit="CSW Enable", initValue=0)

# NetworkManager
class NM:
    ControlAppMsgStopSending: VarSchema = VarSchema("NM::ControlAppMsgStopSending", datatype="int", min=0, max=1, Unit="Stop sending control app messages", initValue=0)
    ControlNMMsgStopSending: VarSchema = VarSchema("NM::ControlNMMsgStopSending", datatype="int", min=0, max=1, Unit="Stop sending control NM messages", initValue=0)
    ResetECU: VarSchema = VarSchema("NM::ResetECU", datatype="int", min=0, max=1, Unit="Reset ECU", initValue=0)

def build_schema_index(*groups) -> Dict[str, VarSchema]:
    index: Dict[str, VarSchema] = {}
    for g in groups:
        for _, v in vars(g).items():
            if isinstance(v, VarSchema):
                index[v.path] = v
    return index

SCHEMA_INDEX = build_schema_index(Simulink, DriverAction, FunctionSwitch, NM)

# 校验与透传
def _coerce(schema: VarSchema, value: Any) -> Any:
    if schema.datatype == "bool":
        if isinstance(value, bool): return value
        if value in (0, 1): return bool(value)
        raise CANoeError("expect bool/0/1")
    if schema.datatype == "int":
        if isinstance(value, bool): raise CANoeError("bool not allowed for int")
        if isinstance(value, int): return value
        if isinstance(value, float) and value.is_integer(): return int(value)
        raise CANoeError("expect int")
    if schema.datatype == "float":
        if isinstance(value, bool): raise CANoeError("bool not allowed for float")
        if isinstance(value, (int, float)): return float(value)
        raise CANoeError("expect float")
    if schema.datatype == "str":
        if isinstance(value, str): return value
        raise CANoeError("expect str")
    raise CANoeError("unknown datatype")

def _check_bounds(schema: VarSchema, value: Any) -> None:
    if schema.allowed is not None:
        if value not in schema.allowed:
            raise CANoeError(f"value {value!r} not in {sorted(schema.allowed)!r}")
        return
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if schema.min is not None and value < schema.min:
            raise CANoeError(f"{value} < min {schema.min}")
        if schema.max is not None and value > schema.max:
            raise CANoeError(f"{value} > max {schema.max}")

class ValidatingCANoeController:
    def __init__(self, inner, schema_index: Dict[str, VarSchema] = SCHEMA_INDEX):
        self._inner = inner
        self._schema_index = schema_index

    # 支持传 path 或 VarSchema
    def write_system_variable(self, target, value: Any) -> None:
        if isinstance(target, VarSchema):
            schema, path = target, target.path
        else:
            schema, path = self._schema_index.get(target), target
        if schema:
            # try:
            v = _coerce(schema, value); _check_bounds(schema, v)
            # except Exception as e:
            #     raise CANoeError(f"Failed to write system variable '{path}': {e}")
            self._inner.write_system_variable(path, v)
        else:
            self._inner.write_system_variable(path, value)

    def read_system_variable(self, target):
        path = target.path if isinstance(target, VarSchema) else target
        val = self._inner.read_system_variable(path)
        schema = self._schema_index.get(path)
        if schema:
            v = _coerce(schema, val); _check_bounds(schema, v); return v
        return val

    def __getattr__(self, name: str):
        return getattr(self._inner, name)
