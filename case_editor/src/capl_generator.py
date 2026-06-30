"""
CAPL 生成器

根据 generate_capl 的配置（按发送节点组织）以及项目里的系统变量文件（.vsysvar），
为每个发送节点生成一个独立的 CANoe CAPL 节点文件（.can）。

设计要点：
- 信号清单与元数据（Factor/Offset、Rv 的 min/max、是否有 special/inactive）全部从
  .vsysvar 文件解析得到，运行时不依赖原始 DBC。
- CAN 通道号从项目的 project.json -> canoe.dbc_files 读取（channel 为 0 基，实际通道 = channel + 1）。
- 每个报文按系统变量进行模拟发送：
    * 节点/报文开关：<ns>_Node_On、<ns>_Node_Info.<sender>_MsgOn、<msg>_Info.<msg>_MsgOn/_MsgOff
    * 发送类型：当前仅实现 Cycle（MsgSendType == 0），周期取 <msg>_Info.<msg>_MsgCycleTime
    * 信号取值优先级：use_special_value > use_inactive_value > Rv（均为原始值，写入 .raw）
    * counter 在 [min,max] 间递增到顶再回到 min
    * checksum 使用通用参数化 CRC16（poly/init/refIn/refOut/xorOut）
- Pv/Rv 通过各自的 _Factor/_Offset 系统变量双向联动，并做防抖避免 on sysvar 互相触发死循环。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET


# ----------------------------------------------------------------------------
# 数据模型
# ----------------------------------------------------------------------------

# 单个信号在 .vsysvar 报文结构里的成员后缀（带前导下划线）。
# 注意：匹配时必须按“长后缀优先”，否则 _special_value 会错误命中 _has_special_value。
_SIGNAL_SUFFIXES = [
    "_has_special_value",
    "_use_special_value",
    "_has_inactive_value",
    "_use_inactive_value",
    "_special_value",
    "_inactive_value",
    "_Factor",
    "_Offset",
    "_Pv",
    "_Rv",
]


@dataclass
class SignalModel:
    """报文中的单个信号及其系统变量元数据。"""
    name: str
    factor: str = "1"
    offset: str = "0"
    rv_min: Optional[str] = None
    rv_max: Optional[str] = None
    pv_is_int: bool = True
    has_special_value: bool = False   # 是否存在 _special_value 成员
    has_inactive_value: bool = False  # 是否存在 _inactive_value 成员
    has_pv: bool = False
    has_rv: bool = False


@dataclass
class MessageModel:
    """一条报文：名称 + 有序信号列表。"""
    name: str
    signals: List[SignalModel] = field(default_factory=list)
    signal_index: Dict[str, SignalModel] = field(default_factory=dict)

    def get(self, signal_name: str) -> Optional[SignalModel]:
        return self.signal_index.get(signal_name)


@dataclass
class ParsedSysvar:
    """.vsysvar 解析结果。"""
    messages: Dict[str, MessageModel] = field(default_factory=dict)
    variable_names: set = field(default_factory=set)   # 所有 variable 的名称
    member_names: set = field(default_factory=set)      # 所有 structMember 的名称


# ----------------------------------------------------------------------------
# .vsysvar 解析
# ----------------------------------------------------------------------------

def _split_signal_member(member_name: str) -> Optional[Tuple[str, str]]:
    """把成员名拆为 (信号名, 后缀)。无法识别返回 None。"""
    for suffix in _SIGNAL_SUFFIXES:
        if member_name.endswith(suffix):
            return member_name[: -len(suffix)], suffix
    return None


def parse_vsysvar(vsysvar_path: str) -> ParsedSysvar:
    """解析 .vsysvar。

    报文名取自报文数据结构对应的 variable 名（如 IPB_0x10C）。
    同时收集所有 variable 名与 structMember 名，便于生成时判断门控变量是否存在。
    """
    content = _read_text_any_encoding(vsysvar_path)
    root = ET.fromstring(content)

    result = ParsedSysvar()

    # 1) 收集所有 struct 定义：struct 名(小写) -> 有序成员元素列表
    structs: Dict[str, List[ET.Element]] = {}
    for struct in root.iter("struct"):
        struct_name = struct.get("name", "")
        if not struct_name:
            continue
        members = list(struct.findall("./structMember"))
        structs[struct_name.lower()] = members
        for member in members:
            name = member.get("name", "")
            if name:
                result.member_names.add(name)

    for variable in root.iter("variable"):
        name = variable.get("name", "")
        if name:
            result.variable_names.add(name)

    # 2) 找到所有“报文数据变量”：type=struct 且 structDefinition 指向的 struct 名
    #    等于变量名的小写（报文数据结构命名规则为 message.name.lower()）。
    for variable in root.iter("variable"):
        if variable.get("type") != "struct":
            continue
        var_name = variable.get("name", "")
        struct_def = variable.get("structDefinition", "")
        if not var_name or not struct_def:
            continue
        struct_simple = struct_def.split("::")[-1].lower()
        # 仅认报文数据结构：struct 名 == 变量名小写；排除 *_info / *_node_info 等
        if struct_simple != var_name.lower():
            continue
        members = structs.get(struct_simple)
        if members is None:
            continue
        model = _build_message_model(var_name, members)
        if model.signals:
            result.messages[var_name] = model
    return result


def _build_message_model(message_name: str, members: List[ET.Element]) -> MessageModel:
    model = MessageModel(name=message_name)
    node_member = f"{message_name}_node"

    for member in members:
        member_name = member.get("name", "")
        if not member_name or member_name == node_member:
            continue  # 跳过发送节点字符串成员
        split = _split_signal_member(member_name)
        if split is None:
            continue
        signal_name, suffix = split
        signal = model.signal_index.get(signal_name)
        if signal is None:
            signal = SignalModel(name=signal_name)
            model.signal_index[signal_name] = signal
            model.signals.append(signal)
        _apply_member(signal, suffix, member)

    return model


def _apply_member(signal: SignalModel, suffix: str, member: ET.Element) -> None:
    if suffix == "_Pv":
        signal.has_pv = True
        signal.pv_is_int = member.get("type", "int") == "int"
    elif suffix == "_Rv":
        signal.has_rv = True
        signal.rv_min = member.get("minValue")
        signal.rv_max = member.get("maxValue")
    elif suffix == "_Factor":
        signal.factor = member.get("startValue", "1")
    elif suffix == "_Offset":
        signal.offset = member.get("startValue", "0")
    elif suffix == "_special_value":
        signal.has_special_value = True
    elif suffix == "_inactive_value":
        signal.has_inactive_value = True


def _read_text_any_encoding(path: str) -> str:
    with open(path, "rb") as fh:
        data = fh.read()
    for encoding in ("utf-8-sig", "utf-8", "gbk", "gb18030", "utf-16", "latin-1"):
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return data.decode("utf-8", errors="replace")


# ----------------------------------------------------------------------------
# 项目通道映射
# ----------------------------------------------------------------------------

def load_channel_mapping(project_path: Path) -> Dict[str, int]:
    """从 project.json 读取 {dbc文件名(小写): 实际CAN通道号}。

    project.json 里 canoe.dbc_files 的 channel 为 0 基，实际通道号 = channel + 1。
    """
    mapping: Dict[str, int] = {}
    project_json = project_path / "project.json"
    if not project_json.exists():
        return mapping
    try:
        with open(project_json, "r", encoding="utf-8") as fh:
            config = json.load(fh)
    except Exception:
        return mapping

    dbc_files = (config.get("canoe", {}) or {}).get("dbc_files", {}) or {}
    if isinstance(dbc_files, dict):
        entries = dbc_files.values()
    else:  # 兼容旧的列表格式
        entries = [{"path": p, "channel": 0} for p in dbc_files]

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        path = entry.get("path", "")
        if not path:
            continue
        channel = entry.get("channel", 0) or 0
        mapping[Path(path).name.lower()] = int(channel) + 1
    return mapping


def resolve_channel(dbc_path: str, channel_mapping: Dict[str, int]) -> int:
    """按文件名匹配通道；找不到默认返回 1。"""
    return channel_mapping.get(Path(dbc_path.replace("\\", "/")).name.lower(), 1)


# ----------------------------------------------------------------------------
# CAPL 代码片段生成
# ----------------------------------------------------------------------------

def _sysvar(namespace: str, variable: str, member: Optional[str] = None) -> str:
    base = f"@{namespace}::{variable}"
    return f"{base}.{member}" if member else base


def _msg_var(message_name: str) -> str:
    return f"msg_{message_name}"


def _info_var(message_name: str) -> str:
    return f"{message_name}_Info"


def _to_capl_number(text: Optional[str], default: str) -> str:
    if text is None or text == "":
        return default
    return text


def _format_float(text: Optional[str], default: str) -> str:
    """把 Factor/Offset 文本规范化为 CAPL 浮点字面量。"""
    if text is None or text == "":
        return default
    try:
        float(text)
        return text.strip()
    except ValueError:
        return default


def _to_capl_int_literal(value: str) -> str:
    """把 0x..., 'true'/'false', 十进制等规范化为 CAPL 整型字面量。"""
    v = value.strip().lower()
    if v in ("true", "1"):
        return "1"
    if v in ("false", "0"):
        return "0"
    if v.startswith("0x"):
        return value.strip()
    try:
        return str(int(float(value)))
    except ValueError:
        return "0"


# 校验库（自动生成，被各 .can 文件 include）。
# - 查表版 CRC16-CCITT：poly 0x1021 / init 0xFFFF / xorOut 0x0000，可由参数变更。
# - sum 校验：逐字节求和后取反（^0xFF）。
CHECKSUM_LIB = """/*@!Encoding:65001*/
/*
 * 报文校验库（自动生成，请勿手改）。
 * 1) PROJ_CRC16_CCITT：查表法 CRC16-CCITT，poly/init/xorOut 可由调用参数控制。
 * 2) PROJ_Checksum    ：逐字节求和后取反（sum ^ 0xFF）。
 */

variables
{
  word gCrc1021Table[256];
  byte gCrcTableReady = 0;
  dword gCrcTablePoly = 0;
}

void BuildCrc16Table(dword poly)
{
  long i, b;
  word crc;

  for (i = 0; i < 256; i++)
  {
    crc = (word)((i << 8) & 0xFFFF);
    for (b = 0; b < 8; b++)
    {
      if (crc & 0x8000)
        crc = (word)(((crc << 1) ^ poly) & 0xFFFF);
      else
        crc = (word)((crc << 1) & 0xFFFF);
    }
    gCrc1021Table[i] = crc;
  }
  gCrcTablePoly = poly;
  gCrcTableReady = 1;
}

// 查表法 CRC16-CCITT（非反射）。init/poly/xorOut 由调用方传入，便于按报文配置变更。
word PROJ_CRC16_CCITT(byte data[], long len, dword init, dword poly, dword xorOut)
{
  word crc;
  long i;
  byte idx;

  // 多项式变化时（或首次调用）重建查找表。
  if (!gCrcTableReady || gCrcTablePoly != poly)
    BuildCrc16Table(poly);

  crc = (word)(init & 0xFFFF);
  for (i = 0; i < len; i++)
  {
    idx = (byte)(((crc >> 8) ^ data[i]) & 0xFF);
    crc = (word)(((crc << 8) ^ gCrc1021Table[idx]) & 0xFFFF);
  }
  return (word)((crc ^ xorOut) & 0xFFFF);
}

// sum 校验：逐字节求和后取反。
byte PROJ_Checksum(byte data[], long len)
{
  byte sum;
  long i;

  sum = 0;
  for (i = 0; i < len; i++)
    sum = (byte)((sum + data[i]) & 0xFF);
  return (byte)(sum ^ 0xFF);
}
"""


def _build_fill_function(
    namespace: str,
    message_name: str,
    model: MessageModel,
    counter_signal: str,
    check_signal: str,
    check_method: str,
    check_parameters: Dict[str, Any],
) -> List[str]:
    """生成填充并发送一条报文的函数体（设置信号、counter、checksum）。"""
    msg = _msg_var(message_name)
    cnt_var = f"cnt_{message_name}"
    lines: List[str] = []
    lines.append(f"void fill_{message_name}()")
    lines.append("{")
    lines.append("  byte _data[64];")
    lines.append("  long _i, _n;")
    lines.append("  dword _crc;")
    lines.append("")

    has_counter = bool(counter_signal) and model.get(counter_signal) is not None
    # 若 checksum 与 counter 是同一个信号（DBC 配置异常），优先按 checksum 处理。
    has_checksum = bool(check_signal) and model.get(check_signal) is not None
    if has_counter and has_checksum and counter_signal == check_signal:
        has_counter = False

    # 1) 普通信号：special > inactive > Rv
    for signal in model.signals:
        if signal.name in (counter_signal, check_signal):
            continue
        lines.extend(_build_signal_assignment(namespace, message_name, signal))

    # 2) counter：写当前值，再在 [min,max] 间递增/回绕
    if has_counter:
        counter = model.get(counter_signal)
        cmin = _to_capl_number(counter.rv_min, "0")
        cmax = _to_capl_number(counter.rv_max, "255")
        lines.append(f"  {msg}.{counter_signal}.raw = {cnt_var};")
        lines.append(f"  if ({cnt_var} >= {cmax})")
        lines.append(f"    {cnt_var} = {cmin};")
        lines.append("  else")
        lines.append(f"    {cnt_var} = {cnt_var} + 1;")

    # 3) checksum：先清零，再对整条报文数据计算校验值。
    #    覆盖范围当前为“整条报文数据字节（校验字段已清零）”。如需排除 counter / 含 DataID，
    #    仅需调整下面读取 _data 的范围与 _n。
    if has_checksum:
        method = (check_method or "crc16").strip().lower()
        params = check_parameters or {}
        lines.append("")
        lines.append(f"  {msg}.{check_signal}.raw = 0;")
        lines.append(f"  _n = {msg}.dlc;")
        lines.append("  for (_i = 0; _i < _n; _i++)")
        lines.append(f"    _data[_i] = {msg}.byte(_i);")
        if "crc" in method:
            poly = _to_capl_int_literal(str(params.get("poly", "0x1021")))
            init = _to_capl_int_literal(str(params.get("init", "0xFFFF")))
            xor_out = _to_capl_int_literal(str(params.get("xorOut", "0x0000")))
            lines.append(
                f"  _crc = PROJ_CRC16_CCITT(_data, _n, {init}, {poly}, {xor_out});"
            )
        else:  # sum 校验
            lines.append("  _crc = PROJ_Checksum(_data, _n);")
        lines.append(f"  {msg}.{check_signal}.raw = _crc;")

    lines.append("}")
    lines.append("")
    return lines


def _build_signal_assignment(namespace: str, message_name: str, signal: SignalModel) -> List[str]:
    msg = _msg_var(message_name)
    rv = _sysvar(namespace, message_name, f"{signal.name}_Rv")
    target = f"{msg}.{signal.name}.raw"
    lines: List[str] = []

    branches: List[Tuple[str, str]] = []
    if signal.has_special_value:
        use_special = _sysvar(namespace, message_name, f"{signal.name}_use_special_value")
        special_value = _sysvar(namespace, message_name, f"{signal.name}_special_value")
        branches.append((f"{use_special} == 1", special_value))
    if signal.has_inactive_value:
        use_inactive = _sysvar(namespace, message_name, f"{signal.name}_use_inactive_value")
        inactive_value = _sysvar(namespace, message_name, f"{signal.name}_inactive_value")
        branches.append((f"{use_inactive} == 1", inactive_value))

    if not branches:
        lines.append(f"  {target} = {rv};")
        return lines

    for idx, (cond, value) in enumerate(branches):
        keyword = "if" if idx == 0 else "else if"
        lines.append(f"  {keyword} ({cond})")
        lines.append(f"    {target} = {value};")
    lines.append("  else")
    lines.append(f"    {target} = {rv};")
    return lines


def _build_linkage_handlers(namespace: str, message_name: str, model: MessageModel) -> List[str]:
    """为每个同时具备 Pv/Rv 的信号生成双向联动 on sysvar 处理器。

    换算的 Factor/Offset 直接采用系统变量文件里的常量（生成时确定），不在运行时再读取
    _Factor/_Offset 系统变量。
    """
    lines: List[str] = []
    for signal in model.signals:
        if not (signal.has_pv and signal.has_rv):
            continue
        try:
            factor = float(signal.factor)
        except (TypeError, ValueError):
            factor = 1.0
        try:
            offset = float(signal.offset)
        except (TypeError, ValueError):
            offset = 0.0
        # Factor 为 0 无法换算，跳过该信号的联动。
        if factor == 0:
            continue

        pv = _sysvar(namespace, message_name, f"{signal.name}_Pv")
        rv = _sysvar(namespace, message_name, f"{signal.name}_Rv")
        factor_lit = _format_float(signal.factor, "1")
        offset_lit = _format_float(signal.offset, "0")
        sv_pv = f"{namespace}::{message_name}.{signal.name}_Pv"
        sv_rv = f"{namespace}::{message_name}.{signal.name}_Rv"

        # Pv 改变 -> 重算 Rv（Rv = round((Pv - Offset)/Factor)），并夹到 Rv 的 min/max。
        lines.append(f"on sysvar {sv_pv}")
        lines.append("{")
        lines.append("  long _newRv;")
        lines.append(f"  _newRv = round(({pv} - ({offset_lit})) / ({factor_lit}));")
        if signal.rv_min is not None and signal.rv_min != "":
            lines.append(f"  if (_newRv < {signal.rv_min})")
            lines.append(f"    _newRv = {signal.rv_min};")
        if signal.rv_max is not None and signal.rv_max != "":
            lines.append(f"  if (_newRv > {signal.rv_max})")
            lines.append(f"    _newRv = {signal.rv_max};")
        lines.append(f"  if (_newRv != {rv})")
        lines.append(f"    {rv} = _newRv;")
        lines.append("}")
        lines.append("")

        # Rv 改变 -> 重算 Pv（Pv = Rv*Factor + Offset）
        lines.append(f"on sysvar {sv_rv}")
        lines.append("{")
        lines.append("  double _newPv;")
        lines.append(f"  _newPv = {rv} * ({factor_lit}) + ({offset_lit});")
        lines.append(f"  if (_newPv != {pv})")
        lines.append(f"    {pv} = _newPv;")
        lines.append("}")
        lines.append("")
    return lines


def _build_can_file(
    dbc_name: str,
    sender_node: str,
    channel: int,
    messages: List[Tuple[Dict[str, Any], MessageModel]],
    parsed: "ParsedSysvar",
) -> str:
    """生成单个发送节点的 .can 文件内容。"""
    namespace = dbc_name
    out: List[str] = []
    out.append("/*@!Encoding:65001*/")
    out.append(f"/* 自动生成：{dbc_name} 网络中 {sender_node} 节点的报文模拟发送 */")
    out.append("")
    out.append("includes")
    out.append("{")
    out.append('  #include "checksum_lib.cin"')
    out.append("}")
    out.append("")

    # variables 块
    out.append("variables")
    out.append("{")
    for msg_cfg, model in messages:
        name = model.name
        out.append(f"  message {name} {_msg_var(name)};")
        out.append(f"  msTimer tmr_{name};")
        out.append(f"  long cnt_{name};")
    out.append("}")
    out.append("")

    # on start：设置通道、初始化 counter、装载定时器
    out.append("on start")
    out.append("{")
    for msg_cfg, model in messages:
        name = model.name
        counter_signal = msg_cfg.get("counter_signal", "")
        counter = model.get(counter_signal) if counter_signal else None
        cmin = _to_capl_number(counter.rv_min, "0") if counter else "0"
        out.append(f"  {_msg_var(name)}.CAN = {channel};")
        out.append(f"  cnt_{name} = {cmin};")
        out.append(f"  arm_{name}();")
    out.append("}")
    out.append("")

    # 每条报文：装载函数 + 定时器事件 + 发送函数 + 填充函数
    for msg_cfg, model in messages:
        name = model.name
        out.extend(_build_arm_function(namespace, name, parsed))
        out.extend(_build_timer_handler(name))
        out.extend(_build_send_function(namespace, dbc_name, sender_node, name, parsed))
        out.extend(
            _build_fill_function(
                namespace,
                name,
                model,
                msg_cfg.get("counter_signal", ""),
                msg_cfg.get("check_signal", ""),
                msg_cfg.get("check_method", "crc16"),
                msg_cfg.get("check_parameters", {}),
            )
        )

    # Pv/Rv 联动
    for msg_cfg, model in messages:
        out.extend(_build_linkage_handlers(namespace, model.name, model))

    return "\n".join(out) + "\n"


def _build_arm_function(namespace: str, message_name: str, parsed: "ParsedSysvar") -> List[str]:
    info = _info_var(message_name)
    if info in parsed.variable_names:
        cycle_expr = _sysvar(namespace, info, f"{message_name}_MsgCycleTime")
    else:
        cycle_expr = "10"  # 无 *_Info 时使用默认周期
    return [
        f"void arm_{message_name}()",
        "{",
        "  long _ct;",
        f"  _ct = {cycle_expr};",
        "  if (_ct <= 0)",
        "    _ct = 10;",
        f"  setTimer(tmr_{message_name}, _ct);",
        "}",
        "",
    ]


def _build_timer_handler(message_name: str) -> List[str]:
    return [
        f"on timer tmr_{message_name}",
        "{",
        f"  send_{message_name}();",
        f"  arm_{message_name}();",
        "}",
        "",
    ]


def _build_send_function(
    namespace: str,
    dbc_name: str,
    sender_node: str,
    message_name: str,
    parsed: "ParsedSysvar",
) -> List[str]:
    info = _info_var(message_name)
    node_info = f"{dbc_name}_Node_Info"
    node_on = f"{dbc_name}_Node_On"
    lines = [f"void send_{message_name}()", "{"]
    # 节点级总开关（仅当系统变量存在时才生成）
    if node_on in parsed.variable_names:
        lines.append(f"  if ({_sysvar(namespace, node_on)} != 1) return;")
    # 发送节点开关（仅当 <sender>_MsgOn 成员存在时才生成）
    if f"{sender_node}_MsgOn" in parsed.member_names:
        lines.append(f"  if ({_sysvar(namespace, node_info, sender_node + '_MsgOn')} != 1) return;")
    # 报文开关（仅当 <msg>_Info 存在时才生成）
    if info in parsed.variable_names:
        lines.append(f"  if ({_sysvar(namespace, info, message_name + '_MsgOn')} != 1) return;")
        lines.append(f"  if ({_sysvar(namespace, info, message_name + '_MsgOff')} == 1) return;")
        # 仅 Cycle 类型（MsgSendType == 0）
        lines.append(f"  if ({_sysvar(namespace, info, message_name + '_MsgSendType')} != 0) return;")
    lines.append(f"  fill_{message_name}();")
    lines.append(f"  output({_msg_var(message_name)});")
    lines.append("}")
    lines.append("")
    return lines


# ----------------------------------------------------------------------------
# 入口
# ----------------------------------------------------------------------------

def generate_capl(config: Dict[str, Any], project_path) -> List[str]:
    """根据配置为每个发送节点生成 .can 文件。

    Args:
        config: 见模块/项目说明，按发送节点组织，含 selected_system_variable_file。
        project_path: 项目根路径（用于读取 project.json 通道映射与写出文件）。

    Returns:
        List[str]: 生成的 .can 文件路径列表（同时会生成共享的 checksum_lib.cin）。
    """
    project_path = Path(project_path)
    output_dir = project_path / "CANoe" / "capl"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 共享 CRC 库
    lib_path = output_dir / "checksum_lib.cin"
    lib_path.write_text(CHECKSUM_LIB, encoding="utf-8")

    # 解析系统变量文件
    sysvar_file = config.get("selected_system_variable_file", "")
    if sysvar_file and Path(sysvar_file).exists():
        parsed = parse_vsysvar(sysvar_file)
    else:
        raise FileNotFoundError(f"系统变量文件不存在或未配置: {sysvar_file!r}")
    messages_by_name = parsed.messages

    channel_mapping = load_channel_mapping(project_path)

    generated: List[str] = []
    for dbc_config in config.get("dbc_configs", []):
        dbc_name = dbc_config.get("dbc_name", "")
        dbc_path = dbc_config.get("dbc_path", "")
        channel = resolve_channel(dbc_path, channel_mapping)

        for sender in dbc_config.get("senders", []):
            sender_node = sender.get("sender_node", "")
            messages: List[Tuple[Dict[str, Any], MessageModel]] = []
            for msg_cfg in sender.get("messages", []):
                msg_name = msg_cfg.get("message_name", "")
                model = messages_by_name.get(msg_name)
                if model is None:
                    print(f"[capl_generator] 警告：系统变量文件中未找到报文 {msg_name}，已跳过")
                    continue
                messages.append((msg_cfg, model))

            if not messages:
                continue

            content = _build_can_file(dbc_name, sender_node, channel, messages, parsed)
            file_path = output_dir / f"{dbc_name}_{sender_node}.can"
            file_path.write_text(content, encoding="utf-8")
            generated.append(str(file_path))

    return generated
