from dataclasses import dataclass
import json
from typing import Any, Dict, List, Optional
from error_manager import CaseDataParseError

@dataclass
class CaseMeta:
    test_point: str
    scenario_id: str
    scenario_name: str
    owner: str
    priority: str
    signals: Dict
    record: Optional[str]
    ai_analysis: Optional[str]
    use_preset: Optional[str]
    case_id: Optional[str]
    preset_signals: Optional[str]
    preset_scene: Optional[str]
    preset_scene_runtime: Optional[str]

@dataclass
class Assert_H:
    op: str
    value: Any

@dataclass
class After_Detect:
    type: str
    ms: float

@dataclass
class Assignment:
    signal: str
    value: Any
    
@dataclass
class Rel_Distance:
    value: float
    op: str
    
@dataclass
class Checks:
    signal: str
    assert_h: Assert_H = None
    timeoutOfCheck_ms: Optional[float] = None
    is_async: Optional[bool] = None
    checkInTime: Optional[float] = None
    after_detect: Optional[After_Detect] = None
    count: Optional[Dict[str, int]] = None
    wait_ms: Optional[float] = None

@dataclass
class CaseStep:
    id: str
    type: str
    signal: str
    value: Any
    assignments: List[Assignment]
    keep_dynamic: Optional[bool] = True
    rel_lon_distance: Optional[Rel_Distance] = None
    rel_lat_distance: Optional[Rel_Distance] = None
    wait_ms: Optional[float] = None
    inline_checks: Optional[List[str]] = None
    comment: Optional[str] = None
    # assert_h: Optional[Assert_H] = None
    checks: List[Checks] = None
    # timeoutOfCheck_ms: Optional[float] = None
    # checkInTime: Optional[float] = None
    # after_detect: Optional[After_Detect] = None
    # count: Optional[Dict[str, int]] = None

@dataclass
class CaseRecord:
    case_id: str
    meta: CaseMeta
    name: str
    steps: List[CaseStep]
    phase_order: List[str]
    flow: List[str]
    
def _require_dict(obj: Any, ctx: str) -> Dict[str, Any]:
    if not isinstance(obj, dict):
        raise CaseDataParseError(f"{ctx}: must be dict")
    return obj

def _require_path(data: Dict[str, Any], path: str, ctx: str) -> Any:
    node = data
    for key in path.split("."):
        if not isinstance(node, dict):
            raise CaseDataParseError(f"{ctx}: '{path}' expects dict at '{key}'")
        if key not in node or node[key] is None:
            raise CaseDataParseError(f"{ctx}: missing required field '{path}'")
        node = node[key]
    return node

def _require_list(data: Dict[str, Any], key: str, ctx: str) -> List[Any]:
    if key not in data or data[key] is None:
        raise CaseDataParseError(f"{ctx}: missing required field '{key}'")
    val = data[key]
    if not isinstance(val, list):
        raise CaseDataParseError(f"{ctx}: '{key}' must be list")
    return val

def _require_list_of_str(data: Dict[str, Any], key: str, ctx: str) -> List[str]:
    lst = _require_list(data, key, ctx)
    if not all(isinstance(x, str) for x in lst):
        raise CaseDataParseError(f"{ctx}: '{key}' must be List[str]")
    return lst

def _as_str(v: Any, ctx: str, field: str) -> str:
    if not isinstance(v, str):
        raise CaseDataParseError(f"{ctx}: '{field}' must be str")
    return v

def _as_num(v: Any, ctx: str, field: str) -> float:
    if not isinstance(v, (int, float)):
        raise CaseDataParseError(f"{ctx}: '{field}' must be number")
    return float(v)

def _as_bool(v: Any, ctx: str, field: str) -> bool:
    if not isinstance(v, bool):
        raise CaseDataParseError(f"{ctx}: '{field}' must be bool")
    return v

def _expect_absent(step: Dict[str, Any], keys: List[str], ctx: str) -> None:
    bad = [k for k in keys if k in step and step[k] is not None]
    if bad:
        raise CaseDataParseError(f"{ctx}: fields not allowed for this type: {bad}")

def _parse_assert_h(obj: Any, ctx: str) -> Assert_H:
    d = _require_dict(obj, f"{ctx}.assert_h")
    op = _as_str(_require_path(d, "op", f"{ctx}.assert_h"), f"{ctx}.assert_h", "op")
    if op == "eq":
        val = d.get("value")
    elif op == "in":
        val = d.get("values")
    elif op == "range":
        val = {"min":d.get("min"),"max":d.get("max")}
        
    if op not in ("eq", "range", "in"):
        raise CaseDataParseError(f"{ctx}: 'assert_h.op' must be one of '==', '!=', '<', '<=', '>', '>='")
    if op == "in":
        if not isinstance(val, list):
            raise CaseDataParseError(f"{ctx}: if op = in, value must be list")
    elif op == "range":
        if not isinstance(obj, dict):
            raise CaseDataParseError(f"{ctx}: if op = range, value must be dict")
        if "min" not in obj or "max" not in obj:
            raise CaseDataParseError(f"{ctx}: 'range' must have 'min' and 'max'")
        min_val = _as_num(obj["min"], ctx, "min")
        max_val = _as_num(obj["max"], ctx, "max")
        if min_val >= max_val:
            raise CaseDataParseError(f"{ctx}: 'range' min must be less than max")
        val = {"min": min_val, "max": max_val}
    return Assert_H(op=op, value=val)

def _parse_after_detect(step: Dict[str, Any], ctx: str) -> Optional[After_Detect]:
    ad = step
    if ad is None:
        return None
    if not isinstance(ad, dict):
        raise CaseDataParseError(f"{ctx}: 'after_detect' must be dict")
    t = ad.get("type")
    if not isinstance(t, str) or not t:
        raise CaseDataParseError(f"{ctx}: 'after_detect.type' must be non-empty str")
    if "ms" not in ad or ad["ms"] is None:
        raise CaseDataParseError(f"{ctx}: 'after_detect.ms' is required when 'after_detect' is present")
    ms = ad["ms"]
    if not isinstance(ms, (int, float)):
        raise CaseDataParseError(f"{ctx}: 'after_detect.ms' must be number")
    return After_Detect(type=t, ms=float(ms))

def _parse_set_assignments(step: Dict[str, Any], ctx: str) -> List[Dict[str, Any]]:
    assignments = step.get("assignments")
    if not isinstance(assignments, list) or not assignments:
        raise CaseDataParseError(f"{ctx}: 'assignments' must be non-empty List[{{signal,value}}]")
    norm: List[Dict[str, Any]] = []
    for i, it in enumerate(assignments):
        if not isinstance(it, dict):
            raise CaseDataParseError(f"{ctx}: assignments[{i}] must be dict")
        sig = it.get("signal")
        if not isinstance(sig, str) or not sig:
            raise CaseDataParseError(f"{ctx}: assignments[{i}].signal must be non-empty str")
        # value 可为任意标量
        norm.append({"signal": sig, "value": it.get("value")})
    return norm

def _parse_check_checks(step: Dict[str, Any], ctx: str) -> List[Dict[str, Any]]:
    checks = step.get("checks")
    if not isinstance(checks, list) or not checks:
        raise CaseDataParseError(f"{ctx}: 'checks' must be non-empty List[{{signal,value}}]")
    norm: List[Dict[str, Any]] = []
    for i, it in enumerate(checks):
        if not isinstance(it, dict):
            raise CaseDataParseError(f"{ctx}: checks[{i}] must be dict")
        sig = it.get("signal")
        if not isinstance(sig, str) or not sig:
            raise CaseDataParseError(f"{ctx}: checks[{i}].signal must be non-empty str")
        assert_h = it.get("assert_h")
        if not assert_h:
            raise CaseDataParseError(f"{ctx}: checks[{i}].assert_h is required")
        assert_h = _parse_assert_h(assert_h, ctx)

        timeout_ms = None
        if "timeoutOfCheck_ms" in it and it["timeoutOfCheck_ms"] is not None:
            timeout_ms = _as_num(it["timeoutOfCheck_ms"], ctx, "timeoutOfCheck_ms")
            #print(timeout_ms)
            
        checkin_ms = None
        if "checkInTime_ms" in it and it["checkInTime_ms"] is not None:
            checkin_ms = _as_num(it["checkInTime_ms"], ctx, "checkInTime_ms")

        is_async = None
        if "async" in it and it["async"] is not None:
            is_async = _as_bool(it["async"], ctx, "async")

        wait_ms = None
        if "wait_ms" in it and it["wait_ms"] is not None:
            wait_ms = _as_num(it["wait_ms"], ctx, "wait_ms")

        after_detect = None
        if "after_detect" in it and it["after_detect"] is not None:
            after_detect = _parse_after_detect(it["after_detect"], ctx)

        count = None
        if "count" in it and it["count"] is not None:
            d = _require_dict(it["count"], f"{ctx}.count")
            out: Dict[str, int] = {}
            for k in ("exact", "min", "max"):
                if k in d and d[k] is not None:
                    if not isinstance(d[k], int):
                        raise CaseDataParseError(f"{ctx}.count.{k}: must be int")
                    out[k] = d[k]
            count = out

        norm.append({"signal": sig, "assert_h": assert_h, "timeout_ms": timeout_ms, "checkin_ms": checkin_ms, "is_async": is_async, "wait_ms": wait_ms, "after_detect": after_detect, "count": count})
    return norm

def _validate_step(step: Dict[str, Any], case_idx: int, step_idx: int) -> CaseStep:
    ctx = f"case[{case_idx+1}]:steps[{step_idx+1}]"
    if not isinstance(step, dict):
        raise CaseDataParseError(f"{ctx}: step must be dict")

    sid = _as_str(_require_path(step, "id", ctx), ctx, "id")
    stype = _as_str(_require_path(step, "type", ctx), ctx, "type").lower()
    if stype not in ("set", "check"):
        raise CaseDataParseError(f"{ctx}: 'type' must be 'set' or 'check'")
    if stype == "set" and sid[:1] not in ("S", "s"):
        raise CaseDataParseError(f"{ctx}: set step id must start with 'S' or 's'")
    if stype == "check" and sid[:1] not in ("C", "c"):
        raise CaseDataParseError(f"{ctx}: check step id must start with 'C' or 'c'")

    scomment = None
    if "comment" in step and step["comment"] is not None:
        scomment = _as_str(step["comment"], ctx, "comment")

    if stype == "set":
        # signal 可缺省，但 assignments 必须存在且非空
        assignments = _parse_set_assignments(step, ctx)
        top_signal = assignments[0]["signal"]
        top_value = assignments[0]["value"]

        # 若顶层提供了 signal/value，校验与第一个赋值一致（避免歧义）
        if "signal" in step and step["signal"] is not None:
            if not isinstance(step["signal"], str) or not step["signal"]:
                raise CaseDataParseError(f"{ctx}: 'signal' must be non-empty str when present")
            if step["signal"] != top_signal:
                raise CaseDataParseError(f"{ctx}: top-level 'signal' != assignments[0].signal")
        if "value" in step:
            if step["value"] != top_value:
                raise CaseDataParseError(f"{ctx}: top-level 'value' != assignments[0].value")

        wait_ms = None
        if "wait_ms" in step and step["wait_ms"] is not None:
            wait_ms = _as_num(step["wait_ms"], ctx, "wait_ms")
            
        keep_dynamic = None
        if "keep_dynamic" in step and step["keep_dynamic"] is not None:
            keep_dynamic = _as_bool(step["keep_dynamic"], ctx, "keep_dynamic")
            
        rel_lon_dis_value = None
        rel_lon_dis_op = None
        if "rel_lon_distance" in step and step["rel_lon_distance"] is not None:
            rel_lon_dis_value = _as_num(step["rel_lon_distance"]["value"], ctx, "rel_lon_distance")
            rel_lon_dis_op = _as_str(step["rel_lon_distance"]["op"], ctx, "rel_lon_distance_op")
            
        rel_lat_dis_value = None
        rel_lat_dis_op = None
        if "rel_lat_distance" in step and step["rel_lat_distance"] is not None:
            rel_lat_dis_value = _as_num(step["rel_lat_distance"]["value"], ctx, "rel_lat_distance")
            rel_lat_dis_op = _as_str(step["rel_lat_distance"]["op"], ctx, "rel_lat_distance_op")

        inline_checks = None
        if "inline_checks" in step and step["inline_checks"] is not None:
            inline_checks = _require_list_of_str(step, "inline_checks", ctx)

        # set 步骤禁止出现以下字段
        _expect_absent(step, ["assert_h", "checkInTime","timeoutOfCheck_ms", "after_detect", "count"], ctx)

        return CaseStep(
            id=sid,
            type=stype,
            signal=top_signal,
            value=top_value,
            assignments=[Assignment(signal=a["signal"], value=a["value"]) for a in assignments],
            rel_lon_distance=Rel_Distance(value=rel_lon_dis_value, op=rel_lon_dis_op) if rel_lon_dis_value is not None and rel_lon_dis_op is not None else None,
            rel_lat_distance=Rel_Distance(value=rel_lat_dis_value, op=rel_lat_dis_op) if rel_lat_dis_value is not None and rel_lat_dis_op is not None else None,
            wait_ms=wait_ms,
            keep_dynamic=keep_dynamic,
            inline_checks=inline_checks,
            comment=scomment
        )

    ### stype == "check"
    # signal = _as_str(_require_path(step, "signal", ctx), ctx, "signal")
    checks = _parse_check_checks(step, ctx)
    #assert_h = _parse_assert_h(_require_path(step, "assert_h", ctx), ctx)


    # check 步骤禁止出现以下字段
    _expect_absent(step, ["value", "assignments", "keep_dynamic", "rel_distance", "inline_checks"], ctx)

    return CaseStep(
        id=sid,
        type=stype,
        signal=None,
        value=None,
        assignments=[],
        comment=scomment,
        checks=[
            Checks(
                signal=a["signal"], 
                assert_h=a["assert_h"], 
                timeoutOfCheck_ms=a["timeout_ms"], 
                checkInTime=a["checkin_ms"], 
                is_async=a["is_async"],
                wait_ms=a["wait_ms"], 
                after_detect=a["after_detect"], 
                count=a["count"]) for a in checks
            ],
    )

def _validate_meta_signals(signals: Any, ctx: str) -> Dict[str, Any]:
    d = _require_dict(signals, f"{ctx}.signals")
    if "set" not in d or d["set"] is None or "check" not in d or d["check"] is None:
        raise CaseDataParseError(f"{ctx}.meta.signals.set and {ctx}.meta.signals.check: must be non-empty list")
    return d

def validate_case(case_data: Dict[str, Any], idx: int) -> CaseRecord:
    ctx = f"case[{idx+1}]"
    _require_dict(case_data, ctx)

    case_id = _as_str(_require_path(case_data, "case_id", ctx), ctx, "case_id")
    name = _as_str(_require_path(case_data, "name", ctx), ctx, "name")

    meta_d = _require_path(case_data, "meta", ctx)
    _require_dict(meta_d, f"{ctx}.meta")

    meta = CaseMeta(
        test_point=_as_str(_require_path(meta_d, "test_point", ctx), ctx, "meta.test_point"),
        scenario_id=_as_str(_require_path(meta_d, "scenario_id", ctx), ctx, "meta.scenario_id"),
        scenario_name=_as_str(_require_path(meta_d, "scenario_name", ctx), ctx, "meta.scenario_name"),
        owner=_as_str(_require_path(meta_d, "owner", ctx), ctx, "meta.owner"),
        priority=_as_str(_require_path(meta_d, "priority", ctx), ctx, "meta.priority"),
        signals=_validate_meta_signals(meta_d["signals"], ctx),
        record=_as_str(_require_path(meta_d, "record", ctx), ctx, "meta.record") if "record" in meta_d else None,
        ai_analysis=_as_str(_require_path(meta_d, "ai_analysis", ctx), ctx, "meta.ai_analysis") if "ai_analysis" in meta_d else None,
        use_preset=_as_str(_require_path(meta_d, "use_preset", ctx), ctx, "meta.use_preset") if "use_preset" in meta_d else None,
        case_id=_as_str(_require_path(meta_d, "case_id", ctx), ctx, "meta.case_id") if "case_id" in meta_d else None,
        preset_signals=_as_str(_require_path(meta_d, "preset_signals", ctx), ctx, "meta.preset_signals") if "preset_signals" in meta_d else None,
        preset_scene=_as_str(_require_path(meta_d, "preset_scene", ctx), ctx, "meta.preset_scene") if "preset_scene" in meta_d else None,
        preset_scene_runtime=_as_str(_require_path(meta_d, "preset_scene_runtime", ctx), ctx, "meta.preset_scene_runtime") if "preset_scene_runtime" in meta_d else None,
    )
    raw_steps = _require_list(case_data, "steps", ctx)
    steps = [_validate_step(s, idx, i) for i, s in enumerate(raw_steps)]

    phase_order = _require_list_of_str(case_data, "phase_order", ctx)
    flow = _require_list_of_str(case_data, "flow", ctx)

    return CaseRecord(
        case_id=case_id,
        meta=meta,
        name=name,
        steps=steps,
        phase_order=phase_order,
        flow=flow,
    )

if __name__=="__main__":
    case_data = json.loads(open("D:\\Test\\Automation\\case_handler\\json_example\\tc_006.json", "r",encoding='utf-8').read())
    case=validate_case(case_data, 0)
    for s in case.steps:
        print(s.checks)

    steps=[
        CaseStep(
            id='S1', 
            type='set', 
            signal='sys::FunctionSwitch::CSW_Enable_S', 
            value=1, 
            assignments=[
                Assignment(
                    signal='sys::FunctionSwitch::CSW_Enable_S', 
                    value=1)
                ], 
            keep_dynamic=None, 
            rel_lon_distance=None, 
            rel_lat_distance=None, 
            wait_ms=None, 
            inline_checks=None, 
            checks=None), 
        CaseStep(
            id='S2', 
            type='set', 
            signal='sys::DriverAction::gear', 
            value=4, 
            assignments=[
                Assignment(
                    signal='sys::DriverAction::gear', 
                    value=4)
                ], 
            keep_dynamic=None, 
            rel_lon_distance=None, 
            rel_lat_distance=None, 
            wait_ms=500.0, 
            inline_checks=['C1'], 
            checks=None), 
        CaseStep(
            id='S3', 
            type='set', 
            signal='env::E_Control_EPS_EPS_0x06D_EPS_SteerWheelAg_Pv', 
            value=181, 
            assignments=[
                Assignment(
                    signal='env::E_Control_EPS_EPS_0x06D_EPS_SteerWheelAg_Pv', 
                    value=181), 
                Assignment(
                    signal='env::E_Control_EPS_EPS_0x06D_EPS_SteerWheelAgVld_Pv', 
                    value=1)
                ], 
            keep_dynamic=False, 
            rel_lon_distance=None, 
            rel_lat_distance=None, 
            wait_ms=300.0, 
            inline_checks=None, 
            checks=None), 
        CaseStep(
            id='C1', 
            type='check', 
            signal=None, 
            value=None, 
            assignments=[], 
            keep_dynamic=True, 
            rel_lon_distance=None, 
            rel_lat_distance=None, 
            wait_ms=None, 
            inline_checks=None, 
            checks=[
                Checks(
                    signal='sig::CAN 1::ADC_0x29C::CSW_Stats_S', 
                    assert_h=Assert_H(op='eq', value=3), 
                    timeoutOfCheck_ms=5000.0, checkInTime=None, after_detect=None, count=None, wait_ms=None), 
                Checks(
                    signal='sig::CAN 1::ADC_0x29C::DNP_warning_text_info', 
                    assert_h=Assert_H(op='eq', value=3), 
                    timeoutOfCheck_ms=None, 
                    checkInTime=3000.0, 
                    after_detect=None, 
                    count=None, 
                    wait_ms=None)
            ]
        ), 
        CaseStep(
            id='C2', 
            type='check', 
            signal=None, 
            value=None, 
            assignments=[], 
            keep_dynamic=True, 
            rel_lon_distance=None, 
            rel_lat_distance=None, 
            wait_ms=None, 
            inline_checks=None, 
            checks=[
                Checks(
                    signal='sig::CAN 1::ADC_0x29C::CSW_Stats_S', 
                    assert_h=Assert_H(op='eq', value=1), 
                    timeoutOfCheck_ms=None, checkInTime=5000.0, after_detect=None, count=None, wait_ms=5000.0
                )
            ])]
