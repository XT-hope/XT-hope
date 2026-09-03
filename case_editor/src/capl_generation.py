"""
CAPL 生成器

根据 generate_capl 的配置（按发送节点组织）以及项目里的系统变量文件（.vsysvar），
为每个发送节点生成一个独立的 CANoe CAPL 节点文件（.can）。

设计要点：
- 信号清单与元数据（Factor/Offset、Rv 的 min/max、special、SigSendType 等）全部从
  .vsysvar 文件解析得到，运行时不依赖原始 DBC。
- CAN 通道号从项目的 project.json -> canoe.dbc_files 读取（channel 为 0 基，实际通道 = channel + 1）。
- 每个报文按系统变量进行模拟发送，支持 MsgSendType：
    Cycle / Event / IfActive / CE / CA（数值与 DBC GenMsgSendType 一致：0~4）。
    发送类型在生成期从 .vsysvar 的 {Msg}_MsgSendType 起始值解析，按类型生成对应 CAPL，
    运行时不判断报文发送类型。无 {Msg}_MsgSendType 时按纯周期调度（_MsgCycleTime，缺省 10ms）。
- 周期发送：每条报文独立 msTimer。到期先 output（emit）再 fill，帧间隔 = MsgCycleTime。
    IfActive / CA：在 {Sig}_has_inactive_value==1 时，Pv/Rv 跨越 inactive（进入或离开）都触发 burst。
- 信号取值优先级：special > 普通值（不再使用 inactive 赋值）；payload 在 on sysvar 中
  通过 apply_{Msg}_{Sig}() 写 msg.信号.phys = {Sig}_Pv（无 Pv 时退回 raw Rv）；fill 仅 Mux 开关 + counter + checksum。
  prepare 顺序：先 fill（设 Mux/counter/CRC）再 sync（批量 apply，Mux guard 成立后写 payload）。
- emit 前 refresh_crc（payload 在 sysvar 中变更后保证 CRC 与 buffer 一致）；fill 末尾同样 refresh_crc（counter 递增后）。
- counter/checksum 可受 {msg}_WrongCounterFlag / {msg}_WrongCRCFlag 影响（为 1 时在计算结果上 +1）。
- Pv/Rv 通过各自的 _Factor/_Offset 系统变量双向联动；写入对方成员与 finish_burst 恢复 sysvar
  时用 g_sv_quiet_* 计数器屏蔽 on sysvar，避免联动/恢复再次触发 burst。
- Simple Mux（单 group）：周期与普通报文相同；fill_group 写死唯一 multiplexer_id。
  CE OnChange/OnWrite 额外发一帧（触发信号所在 group），不打断周期 timer；额外帧经 fill
  递增 counter 并 refresh_crc，发完后再次 fill 为下周期 prepare，避免 counter 重复。
  CA / Event / IfActive burst 均只发触发 group（或唯一 group）。
  Mux 开关信号不参与 burst 触发与影子恢复；其报文值由 fill_group(mux_id) 驱动，与用户 sysvar 赋值互不干扰。
  多路复用元数据全部来自 .vsysvar（_is_multiplexed / _is_multiplexer / _multiplexer_id），生成期写死。
- MsgOn 控制周期 timer：MsgOn==1 时 fill+sync+arm；MsgOn==0 时 cancelTimer。on start 亦仅在 MsgOn==1 时 prepare+arm。
  emit/send 仍保留 MsgOn/MsgOff 门控作为兜底。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET


# ----------------------------------------------------------------------------
# 数据模型
# ----------------------------------------------------------------------------

# MsgSendType 数值（与 DBC GenMsgSendType / .vsysvar valuetable 一致）
MSG_SEND_CYCLE = 0
MSG_SEND_EVENT = 1
MSG_SEND_IF_ACTIVE = 2
MSG_SEND_CE = 3
MSG_SEND_CA = 4

# 单个信号在 .vsysvar 报文结构里的成员后缀（带前导下划线）。
# 注意：匹配时必须按“长后缀优先”，否则 _special_value 会错误命中 _has_special_value。
_SIGNAL_SUFFIXES = [
    "_has_special_value",
    "_use_special_value",
    "_has_inactive_value",
    "_use_inactive_value",
    "_multiplexer_id",
    "_is_multiplexer",
    "_special_value",
    "_inactive_value",
    "_SigSendType",
    "_Factor",
    "_Offset",
    "_Pv",
    "_Rv",
]

# 参与 Event/CE 触发监听的信号成员后缀（不含 Factor/Offset/has_*/SigSendType 等元数据）
_WATCHABLE_SUFFIXES = ("_Pv", "_Rv", "_use_special_value")


@dataclass
class SigSendTypeTable:
    """从 .vsysvar 解析得到的 SigSendType valuetable 及其语义映射。

    数值完全来自 valuetable，生成 CAPL 时只使用此处记录的值，不写死默认映射。
    若 valuetable 中缺少某项，对应字段为 None，生成器跳过依赖该类型的触发分支。
    """
    choices: Dict[int, str] = field(default_factory=dict)
    cycle: Optional[int] = None
    on_write: Optional[int] = None
    on_change: Optional[int] = None
    event: Optional[int] = None


@dataclass
class SignalModel:
    """报文中的单个信号及其系统变量元数据。"""
    name: str
    factor: str = "1"
    offset: str = "0"
    rv_min: Optional[str] = None
    rv_max: Optional[str] = None
    pv_is_int: bool = True
    pv_start: Optional[str] = None
    rv_start: Optional[str] = None
    has_special_value: bool = False
    has_inactive_value: bool = False  # 存在 {Sig}_inactive_value 成员
    has_inactive_flag_member: bool = False  # 存在 {Sig}_has_inactive_value 成员
    inactive_raw: Optional[str] = None
    has_pv: bool = False
    has_rv: bool = False
    has_sig_send_type: bool = False
    sig_send_type: SigSendTypeTable = field(default_factory=SigSendTypeTable)
    is_multiplexer: bool = False
    has_multiplexer_id: bool = False
    multiplexer_id: Optional[int] = None


@dataclass
class MessageInfoModel:
    """报文 *_Info 结构中的发送控制字段。"""
    message_name: str
    has_msg_send_type: bool = False
    msg_send_type_value: int = MSG_SEND_CYCLE
    has_msg_cycle_time: bool = False
    has_msg_cycle_time_fast: bool = False
    has_msg_nr_of_repetition: bool = False
    has_wrong_crc_flag: bool = False
    has_wrong_counter_flag: bool = False
    has_is_multiplexed: bool = False
    is_multiplexed: bool = False


@dataclass
class MuxMetadata:
    """多路复用报文的生成期元数据（来自 .vsysvar，运行时不推断）。"""
    mux_signal_name: str
    mux_signal: SignalModel
    groups: List[int]
    initial_value: str


@dataclass
class MessageModel:
    """一条报文：名称 + 有序信号列表。"""
    name: str
    signals: List[SignalModel] = field(default_factory=list)
    signal_index: Dict[str, SignalModel] = field(default_factory=dict)
    info: Optional[MessageInfoModel] = None
    mux: Optional[MuxMetadata] = None

    def get(self, signal_name: str) -> Optional[SignalModel]:
        return self.signal_index.get(signal_name)


@dataclass
class ParsedSysvar:
    """.vsysvar 解析结果。"""
    messages: Dict[str, MessageModel] = field(default_factory=dict)
    message_infos: Dict[str, MessageInfoModel] = field(default_factory=dict)
    variable_names: set = field(default_factory=set)
    member_names: set = field(default_factory=set)


# ----------------------------------------------------------------------------
# .vsysvar 解析
# ----------------------------------------------------------------------------

def _split_signal_member(member_name: str) -> Optional[Tuple[str, str]]:
    """把成员名拆为 (信号名, 后缀)。无法识别返回 None。"""
    for suffix in _SIGNAL_SUFFIXES:
        if member_name.endswith(suffix):
            return member_name[: -len(suffix)], suffix
    return None


def _parse_value_table(member: ET.Element) -> Dict[int, str]:
    """从 structMember 子节点 valuetable 解析 {数值: 描述}。"""
    table: Dict[int, str] = {}
    vt = member.find("valuetable")
    if vt is None:
        return table
    for entry in vt.findall("valuetableentry"):
        value_text = entry.get("value", "")
        desc = entry.get("description", "") or entry.get("displayString", "") or entry.get("name", "") or ""
        try:
            if value_text.strip().lower().startswith("0x"):
                key = int(value_text.strip(), 16)
            else:
                key = int(float(value_text))
        except (TypeError, ValueError):
            continue
        table[key] = desc.strip()
    return table


def _choice_value_by_name(choices: Dict[int, str], *names: str) -> Optional[int]:
    """按名称（不区分大小写、忽略空格）在 valuetable 中查找数值。"""
    targets = {n.lower().replace(" ", "").replace("_", "") for n in names}
    for value, desc in choices.items():
        normalized = desc.lower().replace(" ", "").replace("_", "")
        if normalized in targets:
            return value
    return None


def _build_sig_send_type_table(choices: Dict[int, str]) -> SigSendTypeTable:
    """根据 valuetable 建立 SigSendType 语义到数值的映射（解析阶段一次性完成）。"""
    return SigSendTypeTable(
        choices=dict(choices),
        cycle=_choice_value_by_name(choices, "Cycle", "Cyclic", "cycle", "cyclic"),
        on_write=_choice_value_by_name(choices, "OnWrite", "onwrite"),
        on_change=_choice_value_by_name(choices, "OnChange", "onchange"),
        event=_choice_value_by_name(choices, "Event", "event"),
    )


def _is_truthy_start_value(text: Optional[str]) -> bool:
    if text is None:
        return False
    value = text.strip().lower()
    if value in ("1", "true"):
        return True
    try:
        return float(value) != 0
    except ValueError:
        return False


def _build_message_info_model(message_name: str, members: List[ET.Element]) -> MessageInfoModel:
    model = MessageInfoModel(message_name=message_name)
    prefix = f"{message_name}_"
    for member in members:
        name = member.get("name", "")
        if not name.startswith(prefix):
            continue
        if name == f"{message_name}_MsgSendType":
            model.has_msg_send_type = True
            model.msg_send_type_value = int(_to_capl_int_literal(member.get("startValue", "0")))
        elif name == f"{message_name}_MsgCycleTime":
            model.has_msg_cycle_time = True
        elif name == f"{message_name}_MsgCycleTimeFast":
            model.has_msg_cycle_time_fast = True
        elif name == f"{message_name}_MsgNrOfRepetition":
            model.has_msg_nr_of_repetition = True
        elif name == f"{message_name}_WrongCRCFlag":
            model.has_wrong_crc_flag = True
        elif name == f"{message_name}_WrongCounterFlag":
            model.has_wrong_counter_flag = True
        elif name == f"{message_name}_is_multiplexed":
            model.has_is_multiplexed = True
            model.is_multiplexed = _is_truthy_start_value(member.get("startValue"))
    return model


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

    # 解析 *_Info 结构（报文发送控制字段）
    for variable in root.iter("variable"):
        if variable.get("type") != "struct":
            continue
        var_name = variable.get("name", "")
        if not var_name.endswith("_Info"):
            continue
        struct_def = variable.get("structDefinition", "")
        if not struct_def:
            continue
        struct_simple = struct_def.split("::")[-1].lower()
        members = structs.get(struct_simple)
        if members is None:
            continue
        msg_name = var_name[: -len("_Info")]
        info_model = _build_message_info_model(msg_name, members)
        result.message_infos[msg_name] = info_model

    # 2) 找到所有“报文数据变量”
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
            model.info = result.message_infos.get(var_name)
            _finalize_mux_metadata(model)
            result.messages[var_name] = model
    return result


def _finalize_mux_metadata(model: MessageModel) -> None:
    """根据 .vsysvar 元数据建立多路复用生成信息（运行时不推断）。"""
    info = model.info
    if info is None or not info.is_multiplexed:
        model.mux = None
        return

    mux_signal: Optional[SignalModel] = None
    groups: set[int] = set()
    for signal in model.signals:
        if signal.is_multiplexer:
            mux_signal = signal
        elif signal.has_multiplexer_id and signal.multiplexer_id is not None:
            groups.add(signal.multiplexer_id)

    if mux_signal is None or not groups:
        model.mux = None
        return

    if mux_signal.has_pv and mux_signal.pv_start is not None:
        initial_value = _to_capl_number(mux_signal.pv_start, "0")
    elif mux_signal.has_rv and mux_signal.rv_start is not None:
        initial_value = _to_capl_number(mux_signal.rv_start, "0")
    else:
        initial_value = "0"

    model.mux = MuxMetadata(
        mux_signal_name=mux_signal.name,
        mux_signal=mux_signal,
        groups=sorted(groups),
        initial_value=initial_value,
    )


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
        signal.pv_start = member.get("startValue")
    elif suffix == "_Rv":
        signal.has_rv = True
        signal.rv_min = member.get("minValue")
        signal.rv_max = member.get("maxValue")
        signal.rv_start = member.get("startValue")
    elif suffix == "_Factor":
        signal.factor = member.get("startValue", "1")
    elif suffix == "_Offset":
        signal.offset = member.get("startValue", "0")
    elif suffix == "_special_value":
        signal.has_special_value = True
    elif suffix == "_inactive_value":
        signal.has_inactive_value = True
        signal.inactive_raw = member.get("startValue")
    elif suffix == "_has_inactive_value":
        signal.has_inactive_flag_member = True
    elif suffix == "_SigSendType":
        signal.has_sig_send_type = True
        signal.sig_send_type = _build_sig_send_type_table(_parse_value_table(member))
    elif suffix == "_is_multiplexer":
        signal.is_multiplexer = _is_truthy_start_value(member.get("startValue"))
    elif suffix == "_multiplexer_id":
        signal.has_multiplexer_id = True
        try:
            signal.multiplexer_id = int(float(member.get("startValue", "0")))
        except (TypeError, ValueError):
            signal.multiplexer_id = 0


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


def resolve_dbc_path(dbc_path: str, project_path: Path) -> Optional[Path]:
    """解析 DBC 文件绝对路径（支持绝对路径、相对项目路径、CANoe/dbc_file 下文件名）。"""
    if not dbc_path:
        return None
    normalized = dbc_path.replace("\\", "/")
    direct = Path(normalized)
    if direct.is_file():
        return direct
    under_project = project_path / normalized
    if under_project.is_file():
        return under_project
    by_name = project_path / "CANoe" / "dbc_file" / Path(normalized).name
    if by_name.is_file():
        return by_name
    return None


def load_message_frame_ids(dbc_path: str, project_path: Path) -> Dict[str, int]:
    """从 DBC 读取 {报文名: frame_id}，用于生成 CAPL 的 message 声明。"""
    resolved = resolve_dbc_path(dbc_path, project_path)
    if resolved is None:
        return {}
    try:
        import cantools

        db = cantools.database.load_file(str(resolved))
    except Exception as exc:
        print(f"[capl_generator] 警告：无法解析 DBC {resolved}: {exc}")
        return {}
    return {msg.name: int(msg.frame_id) for msg in db.messages}


def _resolve_msg_send_type(model: MessageModel) -> int:
    if model.info is not None and model.info.has_msg_send_type:
        return model.info.msg_send_type_value
    return MSG_SEND_CYCLE


def _uses_begin_burst_send(model: MessageModel) -> bool:
    """begin_burst / finish_burst / burst_left 发送路径：Event、IfActive、CA。"""
    return _resolve_msg_send_type(model) in (MSG_SEND_EVENT, MSG_SEND_IF_ACTIVE, MSG_SEND_CA)


def _needs_burst_support(model: MessageModel) -> bool:
    send_type = _resolve_msg_send_type(model)
    return send_type in (MSG_SEND_EVENT, MSG_SEND_IF_ACTIVE, MSG_SEND_CE, MSG_SEND_CA)


def _needs_periodic_scheduler(model: MessageModel) -> bool:
    send_type = _resolve_msg_send_type(model)
    return send_type in (MSG_SEND_CYCLE, MSG_SEND_CE, MSG_SEND_CA)


def _message_decl(message_name: str, frame_id: Optional[int]) -> str:
    """生成 CAPL message 变量声明。

    优先使用 DBC 中的 CAN ID（如 message 0x293 msg_...），避免报文名里含 0x
    （如 CIC_0x293）时被 CAPL 词法解析成十六进制字面量而编译失败。
    """
    var = _msg_var(message_name)
    if frame_id is not None:
        return f"  message 0x{frame_id:X} {var};"
    return f"  message {message_name} {var};"


# ----------------------------------------------------------------------------
# CAPL 代码片段生成
# ----------------------------------------------------------------------------

def _sysvar(namespace: str, variable: str, member: Optional[str] = None) -> str:
    base = f"@{namespace}::{variable}"
    return f"{base}.{member}" if member else base


def _msg_var(message_name: str) -> str:
    return f"msg_{message_name}"


def _counter_enabled(msg_cfg: Dict[str, Any], model: MessageModel) -> bool:
    """该报文是否需要 counter（启用校验且 counter 信号存在于报文中）。"""
    if not msg_cfg.get("has_validation", False):
        return False
    counter_signal = msg_cfg.get("counter_signal", "")
    return bool(counter_signal) and model.get(counter_signal) is not None


def _info_var(message_name: str) -> str:
    return f"{message_name}_Info"


def _info_member_exists(parsed: ParsedSysvar, message_name: str, suffix: str) -> bool:
    return f"{message_name}{suffix}" in parsed.member_names


def _info_sysvar(namespace: str, message_name: str, member: str, parsed: ParsedSysvar, default: str) -> str:
    if _info_member_exists(parsed, message_name, member):
        return _sysvar(namespace, _info_var(message_name), f"{message_name}{member}")
    return default


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


def _phys_expr(raw_expr: str, factor_lit: str, offset_lit: str) -> str:
    """把一个 raw 值表达式转换为物理值表达式：raw*Factor + Offset。

    报文对象的 msg.信号 赋的是物理值（CAPL 会自动编码成 raw 上总线），因此 raw 码
    （special/inactive/counter/checksum 等）需先按各自 Factor/Offset 转成物理值。
    当 Factor==1 且 Offset==0 时直接返回原表达式，保持输出简洁。
    """
    f = (factor_lit or "1").strip()
    o = (offset_lit or "0").strip()
    expr = raw_expr
    if f not in ("1", "1.0"):
        expr = f"({expr}) * ({f})"
    if o not in ("0", "0.0"):
        expr = f"{expr} + ({o})"
    return expr


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


def _burst_mux_var(message_name: str) -> str:
    return f"burst_mux_{message_name}"


def _is_mux_message(model: MessageModel) -> bool:
    return model.mux is not None


def _mux_sysvar_member(namespace: str, message_name: str, mux: MuxMetadata) -> str:
    mux_signal = mux.mux_signal
    if mux_signal.has_pv:
        return _sysvar(namespace, message_name, f"{mux_signal.name}_Pv")
    return _sysvar(namespace, message_name, f"{mux_signal.name}_Rv")


def _build_mux_signal_assignment(
    message_name: str, mux: MuxMetadata, mux_id_expr: str
) -> str:
    msg = _msg_var(message_name)
    return f"  {msg}.{mux.mux_signal_name} = {mux_id_expr};"


def _build_fill_function(
    namespace: str,
    message_name: str,
    model: MessageModel,
    parsed: ParsedSysvar,
    has_validation: bool,
    counter_signal: str,
    check_signal: str,
    check_method: str,
    check_parameters: Dict[str, Any],
) -> List[str]:
    """生成填充报文函数。多路复用报文生成 fill_{msg}_group(long mux_id)。"""
    if _is_mux_message(model):
        return _build_fill_group_function(
            namespace,
            message_name,
            model,
            parsed,
            has_validation,
            counter_signal,
            check_signal,
            check_method,
            check_parameters,
        )
    return _build_fill_plain_function(
        namespace,
        message_name,
        model,
        parsed,
        has_validation,
        counter_signal,
        check_signal,
        check_method,
        check_parameters,
    )


def _build_fill_plain_function(
    namespace: str,
    message_name: str,
    model: MessageModel,
    parsed: ParsedSysvar,
    has_validation: bool,
    counter_signal: str,
    check_signal: str,
    check_method: str,
    check_parameters: Dict[str, Any],
) -> List[str]:
    """生成非多路复用报文的 fill_{message}()。"""
    lines: List[str] = []
    lines.append(f"void fill_{message_name}()")
    lines.append("{")
    lines.extend(
        _build_fill_body_lines(
            namespace,
            message_name,
            model,
            parsed,
            has_validation,
            counter_signal,
            check_signal,
            check_method,
            check_parameters,
            mux_id_expr=None,
        )
    )
    lines.append("}")
    lines.append("")
    return lines


def _build_fill_group_function(
    namespace: str,
    message_name: str,
    model: MessageModel,
    parsed: ParsedSysvar,
    has_validation: bool,
    counter_signal: str,
    check_signal: str,
    check_method: str,
    check_parameters: Dict[str, Any],
) -> List[str]:
    """生成多路复用报文的 fill_{message}_group(long mux_id)。"""
    lines: List[str] = []
    lines.append(f"void fill_{message_name}_group(long mux_id)")
    lines.append("{")
    lines.extend(
        _build_fill_body_lines(
            namespace,
            message_name,
            model,
            parsed,
            has_validation,
            counter_signal,
            check_signal,
            check_method,
            check_parameters,
            mux_id_expr="mux_id",
        )
    )
    lines.append("}")
    lines.append("")
    return lines


def _apply_function_name(message_name: str, signal_name: str) -> str:
    return f"apply_{message_name}_{signal_name}"


def _refresh_crc_function_name(message_name: str) -> str:
    return f"refresh_crc_{message_name}"


def _sync_payload_function_name(message_name: str) -> str:
    return f"sync_{message_name}_payload"


def _message_has_checksum(
    has_validation: bool,
    check_signal: str,
    model: MessageModel,
) -> bool:
    if not has_validation:
        return False
    return bool(check_signal) and model.get(check_signal) is not None


def _iter_payload_signals(
    model: MessageModel,
    counter_signal: str,
    check_signal: str,
) -> List[SignalModel]:
    items: List[SignalModel] = []
    for signal in model.signals:
        if _is_mux_switch_signal(model, signal):
            continue
        if signal.name in (counter_signal, check_signal):
            continue
        if not signal.has_pv and not signal.has_rv:
            continue
        items.append(signal)
    return items


def _build_apply_assignment_lines(
    namespace: str,
    message_name: str,
    signal: SignalModel,
    *,
    indent: str = "  ",
) -> List[str]:
    """生成 apply 函数体：msg.sig.phys = Pv；special 分支；无 Pv 时退回 raw Rv。"""
    msg = _msg_var(message_name)
    target = f"{msg}.{signal.name}"
    lines: List[str] = []

    if signal.has_pv:
        normal_value = f"{target}.phys = {_sysvar(namespace, message_name, f'{signal.name}_Pv')};"
    elif signal.has_rv:
        normal_value = f"{target} = {_sysvar(namespace, message_name, f'{signal.name}_Rv')};"
    else:
        return []

    if signal.has_special_value:
        has_special = _sysvar(namespace, message_name, f"{signal.name}_has_special_value")
        use_special = _sysvar(namespace, message_name, f"{signal.name}_use_special_value")
        special_value = _sysvar(namespace, message_name, f"{signal.name}_special_value")
        if signal.has_pv:
            special_assign = f"{target}.phys = {special_value};"
        else:
            special_assign = f"{target} = {special_value};"
        lines.extend([
            f"{indent}if ({has_special} == 1 && {use_special} == 1)",
            f"{indent}{{",
            f"{indent}  {special_assign}",
            f"{indent}}}",
            f"{indent}else",
            f"{indent}{{",
            f"{indent}  {normal_value}",
            f"{indent}}}",
        ])
    else:
        lines.append(f"{indent}{normal_value}")

    return lines


def _wrap_mux_group_guard_lines(
    message_name: str,
    model: MessageModel,
    signal: SignalModel,
    inner_lines: List[str],
    *,
    indent: str = "  ",
) -> List[str]:
    if model.mux is None or not signal.has_multiplexer_id or signal.multiplexer_id is None:
        return inner_lines
    msg = _msg_var(message_name)
    mux_name = model.mux.mux_signal_name
    guard = f"{msg}.{mux_name} == {signal.multiplexer_id}"
    return [
        f"{indent}if ({guard})",
        f"{indent}{{",
        *inner_lines,
        f"{indent}}}",
    ]


def _build_apply_function(
    namespace: str,
    message_name: str,
    model: MessageModel,
    signal: SignalModel,
) -> List[str]:
    func = _apply_function_name(message_name, signal.name)
    body = _wrap_mux_group_guard_lines(
        message_name,
        model,
        signal,
        _build_apply_assignment_lines(namespace, message_name, signal, indent="    "),
    )
    if not body:
        return []
    lines = [f"void {func}()", "{"]
    lines.extend(body)
    lines.extend(["}", ""])
    return lines


def _build_all_apply_functions(
    namespace: str,
    message_name: str,
    model: MessageModel,
    counter_signal: str,
    check_signal: str,
) -> List[str]:
    lines: List[str] = []
    for signal in _iter_payload_signals(model, counter_signal, check_signal):
        lines.extend(_build_apply_function(namespace, message_name, model, signal))
    return lines


def _build_sync_payload_function(
    message_name: str,
    model: MessageModel,
    counter_signal: str,
    check_signal: str,
) -> List[str]:
    calls = [
        f"  {_apply_function_name(message_name, signal.name)}();"
        for signal in _iter_payload_signals(model, counter_signal, check_signal)
    ]
    if not calls:
        return []
    lines = [f"void {_sync_payload_function_name(message_name)}()", "{"]
    lines.extend(calls)
    lines.extend(["}", ""])
    return lines


def _build_refresh_crc_function(
    namespace: str,
    message_name: str,
    model: MessageModel,
    parsed: ParsedSysvar,
    has_validation: bool,
    check_signal: str,
    check_method: str,
    check_parameters: Dict[str, Any],
) -> List[str]:
    if not _message_has_checksum(has_validation, check_signal, model):
        return []
    msg = _msg_var(message_name)
    method = (check_method or "crc16").strip().lower()
    params = check_parameters or {}
    lines = [
        f"void {_refresh_crc_function_name(message_name)}()",
        "{",
        "  byte _data[64];",
        "  long _i, _n;",
        "  dword _crc;",
        "",
        f"  {msg}.{check_signal} = 0;",
        f"  _n = {msg}.dlc;",
        "  for (_i = 0; _i < _n; _i++)",
        f"    _data[_i] = {msg}.byte(_i);",
    ]
    if "crc" in method:
        poly = _to_capl_int_literal(str(params.get("poly", "0x1021")))
        init = _to_capl_int_literal(str(params.get("init", "0xFFFF")))
        xor_out = _to_capl_int_literal(str(params.get("xorOut", "0x0000")))
        lines.append(f"  _crc = PROJ_CRC16_CCITT(_data, _n, {init}, {poly}, {xor_out});")
    else:
        lines.append("  _crc = PROJ_Checksum(_data, _n);")
    wrong_crc = _info_sysvar(namespace, message_name, "_WrongCRCFlag", parsed, "0")
    if model.info and model.info.has_wrong_crc_flag:
        lines.extend([
            f"  if ({wrong_crc} == 1)",
            "    _crc = _crc + 1;",
        ])
    lines.extend([
        f"  {msg}.{check_signal} = _crc;",
        "}",
        "",
    ])
    return lines


def _build_fill_body_lines(
    namespace: str,
    message_name: str,
    model: MessageModel,
    parsed: ParsedSysvar,
    has_validation: bool,
    counter_signal: str,
    check_signal: str,
    check_method: str,
    check_parameters: Dict[str, Any],
    mux_id_expr: Optional[str],
) -> List[str]:
    """生成 fill 函数体：Mux 开关 + counter + refresh_crc（payload 由 sysvar apply 维护）。"""
    msg = _msg_var(message_name)
    cnt_var = f"cnt_{message_name}"
    mux = model.mux

    if not has_validation:
        counter_signal = ""
        check_signal = ""

    has_counter = bool(counter_signal) and model.get(counter_signal) is not None
    has_checksum = _message_has_checksum(has_validation, check_signal, model)

    lines: List[str] = []

    if mux is not None and mux_id_expr is not None:
        lines.append(_build_mux_signal_assignment(message_name, mux, mux_id_expr))

    if has_counter:
        counter = model.get(counter_signal)
        cmin = _to_capl_number(counter.rv_min, "0")
        cmax = _to_capl_number(counter.rv_max, "255")
        wrong_counter = _info_sysvar(namespace, message_name, "_WrongCounterFlag", parsed, "0")
        if model.info and model.info.has_wrong_counter_flag:
            cnt_assign = f"({cnt_var}) + (({wrong_counter} == 1) ? 1 : 0)"
        else:
            cnt_assign = cnt_var
        lines.append(f"  {msg}.{counter_signal} = {cnt_assign};")
        lines.append(f"  if ({cnt_var} >= {cmax})")
        lines.append(f"    {cnt_var} = {cmin};")
        lines.append("  else")
        lines.append(f"    {cnt_var} = {cnt_var} + 1;")

    if has_checksum:
        if lines:
            lines.append("")
        lines.append(f"  {_refresh_crc_function_name(message_name)}();")

    return lines


def _shadow_var(message_name: str, member_name: str) -> str:
    return f"g_prev_{message_name}_{member_name}"


def _restore_var(message_name: str, member_name: str) -> str:
    return f"g_restore_{message_name}_{member_name}"


def _capl_member_type(signal: SignalModel, suffix: str) -> str:
    if suffix == "_Pv":
        return "int" if signal.pv_is_int else "float"
    if suffix == "_Rv":
        return "long"
    return "long"


def _is_mux_switch_signal(model: MessageModel, signal: SignalModel) -> bool:
    """多路复用报文中的 Mux 开关信号（如 Child_ID_32B_S），不作为普通数据信号处理。"""
    return model.mux is not None and signal.name == model.mux.mux_signal_name


def _watchable_members(
    model: MessageModel,
    exclude: Optional[set] = None,
) -> List[Tuple[SignalModel, str]]:
    """返回需要监听变化的 (信号, 后缀) 列表（不含 Mux 开关信号）。"""
    exclude = exclude or set()
    items: List[Tuple[SignalModel, str]] = []
    for signal in model.signals:
        if signal.name in exclude or _is_mux_switch_signal(model, signal):
            continue
        for suffix in _WATCHABLE_SUFFIXES:
            member = f"{signal.name}{suffix}"
            if suffix == "_Pv" and signal.has_pv:
                items.append((signal, suffix))
            elif suffix == "_Rv" and signal.has_rv:
                items.append((signal, suffix))
            elif suffix == "_use_special_value" and signal.has_special_value:
                items.append((signal, suffix))
    return items


def _inactive_phys_expr(namespace: str, message_name: str, signal: SignalModel) -> str:
    inactive_raw = _sysvar(namespace, message_name, f"{signal.name}_inactive_value")
    return _phys_expr(inactive_raw, _format_float(signal.factor, "1"), _format_float(signal.offset, "0"))


def _inactive_raw_expr(namespace: str, message_name: str, signal: SignalModel) -> str:
    return _sysvar(namespace, message_name, f"{signal.name}_inactive_value")


def _inactive_compare_target(
    namespace: str, message_name: str, signal: SignalModel, suffix: str
) -> Optional[str]:
    """IfActive/CA 用来和 _old/_new 比较的 inactive 表达式。无 _inactive_value 则无法比较。"""
    if not signal.has_inactive_value or suffix not in ("_Pv", "_Rv"):
        return None
    if suffix == "_Pv":
        return _inactive_phys_expr(namespace, message_name, signal)
    return _inactive_raw_expr(namespace, message_name, signal)


def _with_inactive_flag(
    namespace: str, message_name: str, signal: SignalModel, condition: str
) -> str:
    """有 {Sig}_has_inactive_value 时，运行时必须为 1 才启用 inactive 相关判定。"""
    if not signal.has_inactive_flag_member:
        return condition
    flag = _sysvar(namespace, message_name, f"{signal.name}_has_inactive_value")
    return f"{flag} == 1 && {condition}"


def _if_active_edge_condition(inactive_expr: str) -> str:
    """IfActive / CA：inactive ↔ 非 inactive 双向边沿都触发（不含 active→active）。"""
    return (
        f"((_old == ({inactive_expr}) && _new != ({inactive_expr}))"
        f" || (_old != ({inactive_expr}) && _new == ({inactive_expr})))"
    )


def _restore_pending_var(message_name: str, member_name: str) -> str:
    return f"restore_pending_{message_name}_{member_name}"


def _quiet_var(message_name: str) -> str:
    """on sysvar 静默计数：>0 时只更新影子，不触发 burst（覆盖联动写入与 restore）。"""
    return f"g_sv_quiet_{message_name}"


def _message_has_pv_rv_linkage(model: MessageModel, exclude: Optional[set] = None) -> bool:
    exclude = exclude or set()
    for signal in model.signals:
        if signal.name in exclude or _is_mux_switch_signal(model, signal):
            continue
        if signal.has_pv and signal.has_rv and _linkage_factor_ok(signal):
            return True
    return False


def _message_needs_quiet(model: MessageModel, exclude: Optional[set] = None) -> bool:
    return _has_burst_triggers(model) or _message_has_pv_rv_linkage(model, exclude)


def _build_core_burst_timer_variables(message_name: str) -> List[str]:
    """arm / timer / send 始终引用 burst_left / burst_fast，所有带定时器的报文都必须声明。"""
    return [
        f"  long burst_left_{message_name};",
        f"  long burst_fast_{message_name};",
    ]


def _build_burst_variables(
    message_name: str, model: MessageModel, exclude: Optional[set] = None
) -> List[str]:
    lines: List[str] = []
    if _is_mux_message(model):
        lines.append(f"  long {_burst_mux_var(message_name)};")
    for signal, suffix in _watchable_members(model, exclude):
        member = f"{signal.name}{suffix}"
        capl_type = _capl_member_type(signal, suffix)
        lines.append(f"  {capl_type} {_shadow_var(message_name, member)};")
        lines.append(f"  {capl_type} {_restore_var(message_name, member)};")
        lines.append(f"  long {_restore_pending_var(message_name, member)};")
    return lines


def _build_init_shadows(namespace: str, message_name: str, model: MessageModel, exclude: Optional[set] = None) -> List[str]:
    lines: List[str] = []
    for signal, suffix in _watchable_members(model, exclude):
        member = f"{signal.name}{suffix}"
        sv = _sysvar(namespace, message_name, member)
        lines.append(f"  {_shadow_var(message_name, member)} = {sv};")
    return lines


def _build_begin_burst_function(namespace: str, message_name: str, parsed: ParsedSysvar, model: MessageModel) -> List[str]:
    info = _info_var(message_name)
    rep = _info_sysvar(namespace, message_name, "_MsgNrOfRepetition", parsed, "1")
    lines = [
        f"void begin_burst_{message_name}(long use_fast)",
        "{",
        f"  burst_left_{message_name} = {rep};",
        "  if (burst_left_{0} <= 0)".format(message_name),
        f"    burst_left_{message_name} = 1;",
        f"  burst_fast_{message_name} = use_fast;",
        f"  cancelTimer(tmr_{message_name});",
        f"  send_{message_name}();",
        f"  burst_left_{message_name}--;",
        f"  if (burst_left_{message_name} > 0)",
        f"    arm_{message_name}();",
        "  else",
        f"    finish_burst_{message_name}();",
        "}",
        "",
    ]
    return lines


def _build_finish_burst_function(
    namespace: str,
    message_name: str,
    model: MessageModel,
    parsed: ParsedSysvar,
    exclude: Optional[set] = None,
    counter_signal: str = "",
    check_signal: str = "",
) -> List[str]:
    quiet = _quiet_var(message_name)
    send_type = _resolve_msg_send_type(model)
    lines = [f"void finish_burst_{message_name}()", "{"]
    lines.append(f"  {quiet} = {quiet} + 1;")
    for signal, suffix in _watchable_members(model, exclude):
        member = f"{signal.name}{suffix}"
        pending = _restore_pending_var(message_name, member)
        sv = _sysvar(namespace, message_name, member)
        lines.append(f"  if ({pending})")
        lines.append("  {")
        lines.append(f"    {_shadow_var(message_name, member)} = {_restore_var(message_name, member)};")
        lines.append(f"    {sv} = {_restore_var(message_name, member)};")
        lines.append(f"    {pending} = 0;")
        lines.append("  }")
    lines.append(f"  {quiet} = {quiet} - 1;")
    lines.append(f"  burst_fast_{message_name} = 0;")
    if model.mux is not None:
        lines.append(f"  {_burst_mux_var(message_name)} = -1;")
    lines.extend(
        _build_prepare_invoke_lines(
            message_name, model, counter_signal, check_signal, indent="  "
        )
    )
    if send_type in (MSG_SEND_EVENT, MSG_SEND_IF_ACTIVE):
        lines.append("  return;")
    else:
        lines.append(f"  arm_{message_name}();")
    lines.append("}")
    lines.append("")
    return lines


def _linkage_factor_ok(signal: SignalModel) -> bool:
    try:
        return float(signal.factor) != 0
    except (TypeError, ValueError):
        return False


def _has_burst_triggers(model: MessageModel) -> bool:
    return _needs_burst_support(model)


def _build_fill_invoke_lines(message_name: str, model: MessageModel, indent: str = "  ") -> List[str]:
    if model.mux is None:
        return [f"{indent}fill_{message_name}();"]
    if len(model.mux.groups) == 1:
        return [f"{indent}fill_{message_name}_group({model.mux.groups[0]});"]
    return []


def _build_sync_invoke_lines(
    message_name: str,
    model: MessageModel,
    counter_signal: str,
    check_signal: str,
    indent: str = "  ",
) -> List[str]:
    if _iter_payload_signals(model, counter_signal, check_signal):
        return [f"{indent}{_sync_payload_function_name(message_name)}();"]
    return []


def _build_prepare_invoke_lines(
    message_name: str,
    model: MessageModel,
    counter_signal: str,
    check_signal: str,
    indent: str = "  ",
) -> List[str]:
    lines: List[str] = []
    lines.extend(_build_fill_invoke_lines(message_name, model, indent=indent))
    lines.extend(
        _build_sync_invoke_lines(
            message_name, model, counter_signal, check_signal, indent=indent
        )
    )
    return lines


def _build_startup_prepare_lines(
    message_name: str,
    model: MessageModel,
    counter_signal: str,
    check_signal: str,
    indent: str = "  ",
) -> List[str]:
    return _build_prepare_invoke_lines(
        message_name, model, counter_signal, check_signal, indent=indent
    )


def _build_mux_output_all_groups_function(
    message_name: str,
    model: MessageModel,
    counter_signal: str = "",
    check_signal: str = "",
) -> List[str]:
    """生成 Simple Mux 报文 fill + sync + output 辅助函数（仅唯一 group）。"""
    if model.mux is None:
        return []
    msg = _msg_var(message_name)
    group_id = model.mux.groups[0]
    lines = [
        f"void output_all_{message_name}_groups()",
        "{",
        f"  fill_{message_name}_group({group_id});",
    ]
    lines.extend(
        _build_sync_invoke_lines(
            message_name, model, counter_signal, check_signal, indent="  "
        )
    )
    lines.extend([
        f"  output({msg});",
        "}",
        "",
    ])
    return lines


def _append_burst_trigger_decls(
    lines: List[str],
    signal: SignalModel,
    suffix: str,
) -> None:
    capl_type = _capl_member_type(signal, suffix)
    lines.append(f"  {capl_type} _old, _new;")
    lines.append("  long _triggered, _use_fast;")


def _append_burst_trigger_lines(
    lines: List[str],
    namespace: str,
    message_name: str,
    model: MessageModel,
    parsed: ParsedSysvar,
    signal: SignalModel,
    suffix: str,
    member: str,
) -> bool:
    """向 handler 追加 burst 触发语句（不含局部变量声明）。返回是否生成了 burst 逻辑。"""
    if not _needs_burst_support(model):
        return False

    send_type = _resolve_msg_send_type(model)
    shadow = _shadow_var(message_name, member)
    sv = _sysvar(namespace, message_name, member)
    sig_table = signal.sig_send_type if signal.has_sig_send_type else None
    sig_send_type_expr = (
        _sysvar(namespace, message_name, f"{signal.name}_SigSendType") if sig_table else None
    )

    inactive_expr = _inactive_compare_target(namespace, message_name, signal, suffix)
    inactive_edge_cmp = None
    if inactive_expr is not None:
        inactive_edge_cmp = _with_inactive_flag(
            namespace, message_name, signal, _if_active_edge_condition(inactive_expr)
        )

    lines.append(f"  _old = {shadow};")
    lines.append(f"  _new = {sv};")
    lines.append(f"  if ({_quiet_var(message_name)} != 0)")
    lines.append("  {")
    lines.append(f"    {shadow} = _new;")
    lines.append("  }")
    lines.append("  else")
    lines.append("  {")
    lines.append("    _triggered = 0;")
    lines.append("    _use_fast = 0;")

    if send_type == MSG_SEND_EVENT:
        lines.append("    if (_old != _new)")
        lines.append("    {")
        lines.append("      _triggered = 1;")
        lines.append("      _use_fast = 0;")
        lines.append("    }")
    elif send_type == MSG_SEND_IF_ACTIVE and inactive_edge_cmp:
        lines.append(f"    if (_old != _new && ({inactive_edge_cmp}))")
        lines.append("    {")
        lines.append("      _triggered = 1;")
        lines.append("      _use_fast = 0;")
        lines.append("    }")
    elif send_type == MSG_SEND_CE and sig_send_type_expr and sig_table:
        first_branch = True
        if sig_table.on_change is not None:
            keyword = "if" if first_branch else "else if"
            first_branch = False
            lines.append(
                f"    {keyword} ({sig_send_type_expr} == {sig_table.on_change} && _old != _new)"
            )
            lines.append("    {")
            lines.append("      _triggered = 1;")
            lines.append("    }")
        if sig_table.on_write is not None:
            keyword = "if" if first_branch else "else if"
            first_branch = False
            lines.append(f"    {keyword} ({sig_send_type_expr} == {sig_table.on_write})")
            lines.append("    {")
            lines.append("      _triggered = 1;")
            lines.append("    }")
    elif send_type == MSG_SEND_CA and inactive_edge_cmp and sig_send_type_expr and sig_table and sig_table.cycle is not None:
        lines.append(
            f"    if ({sig_send_type_expr} != {sig_table.cycle}"
            f" && _old != _new && ({inactive_edge_cmp}))"
        )
        lines.append("    {")
        lines.append("      _triggered = 1;")
        lines.append("      _use_fast = 1;")
        lines.append("    }")

    lines.append("    if (_triggered)")
    lines.append("    {")
    if send_type == MSG_SEND_CE:
        lines.append(f"      {shadow} = _new;")
        if model.mux is not None:
            if signal.has_multiplexer_id and signal.multiplexer_id is not None:
                mux_group = signal.multiplexer_id
            else:
                mux_group = model.mux.groups[0]
            lines.append(f"      send_additional_{message_name}({mux_group});")
        else:
            lines.append(f"      send_additional_{message_name}();")
    else:
        lines.append(f"      {_restore_pending_var(message_name, member)} = 1;")
        lines.append(f"      {_restore_var(message_name, member)} = _old;")
        lines.append(f"      {shadow} = _new;")
        if model.mux is not None and send_type in (MSG_SEND_EVENT, MSG_SEND_IF_ACTIVE):
            burst_mux = _burst_mux_var(message_name)
            if signal.has_multiplexer_id and signal.multiplexer_id is not None:
                mux_group = signal.multiplexer_id
            else:
                mux_group = model.mux.groups[0]
            lines.append(f"      {burst_mux} = {mux_group};")
        lines.append(f"      begin_burst_{message_name}(_use_fast);")
    lines.append("    }")
    lines.append("    else")
    lines.append(f"      {shadow} = _new;")
    lines.append("  }")
    return True


def _append_pv_to_rv_linkage_decls(lines: List[str]) -> None:
    lines.append("  double _q;")
    lines.append("  long _newRv;")


def _append_pv_to_rv_linkage_lines(
    lines: List[str],
    namespace: str,
    message_name: str,
    signal: SignalModel,
) -> None:
    """Pv 变化时同步 Rv。"""
    pv = _sysvar(namespace, message_name, f"{signal.name}_Pv")
    rv = _sysvar(namespace, message_name, f"{signal.name}_Rv")
    factor_lit = _format_float(signal.factor, "1")
    offset_lit = _format_float(signal.offset, "0")
    quiet = _quiet_var(message_name)
    lines.append(f"  {quiet} = {quiet} + 1;")
    lines.append(f"  _q = ({pv} - ({offset_lit})) / ({factor_lit});")
    lines.append("  if (_q >= 0)")
    lines.append("    _newRv = (long)(_q + 0.5);")
    lines.append("  else")
    lines.append("    _newRv = (long)(_q - 0.5);")
    if signal.rv_min is not None and signal.rv_min != "":
        lines.append(f"  if (_newRv < {signal.rv_min})")
        lines.append(f"    _newRv = {signal.rv_min};")
    if signal.rv_max is not None and signal.rv_max != "":
        lines.append(f"  if (_newRv > {signal.rv_max})")
        lines.append(f"    _newRv = {signal.rv_max};")
    lines.append(f"  if (_newRv != {rv})")
    lines.append(f"    {rv} = _newRv;")
    lines.append(f"  {quiet} = {quiet} - 1;")


def _append_rv_to_pv_linkage_decls(lines: List[str]) -> None:
    lines.append("  double _newPv;")


def _append_rv_to_pv_linkage_lines(
    lines: List[str],
    namespace: str,
    message_name: str,
    signal: SignalModel,
) -> None:
    """Rv 变化时同步 Pv。"""
    pv = _sysvar(namespace, message_name, f"{signal.name}_Pv")
    rv = _sysvar(namespace, message_name, f"{signal.name}_Rv")
    factor_lit = _format_float(signal.factor, "1")
    offset_lit = _format_float(signal.offset, "0")
    quiet = _quiet_var(message_name)
    lines.append(f"  {quiet} = {quiet} + 1;")
    lines.append(f"  _newPv = {rv} * ({factor_lit}) + ({offset_lit});")
    lines.append(f"  if (_newPv != {pv})")
    lines.append(f"    {pv} = _newPv;")
    lines.append(f"  {quiet} = {quiet} - 1;")


def _append_apply_invoke(stmts: List[str], message_name: str, signal: SignalModel, suffix: str) -> None:
    if suffix == "_Pv" and signal.has_pv:
        stmts.append(f"  {_apply_function_name(message_name, signal.name)}();")
    elif suffix == "_use_special_value" and signal.has_special_value:
        stmts.append(f"  {_apply_function_name(message_name, signal.name)}();")


def _build_merged_sysvar_handlers(
    namespace: str,
    message_name: str,
    model: MessageModel,
    parsed: ParsedSysvar,
    exclude: Optional[set] = None,
) -> List[str]:
    """为每个系统变量成员生成唯一的 on sysvar 处理器（burst 触发 + Pv/Rv 联动合并）。

    CAPL 不允许对同一 sysvar 注册多个 on sysvar，因此每个成员最多一个 handler。
    """
    exclude = exclude or set()
    has_burst = _has_burst_triggers(model)
    watchable = {(s.name, suf) for s, suf in _watchable_members(model, exclude)}
    lines: List[str] = []

    for signal in model.signals:
        if signal.name in exclude or _is_mux_switch_signal(model, signal):
            continue

        linkage_ok = signal.has_pv and signal.has_rv and _linkage_factor_ok(signal)

        if signal.has_pv:
            member = f"{signal.name}_Pv"
            sv_path = f"{namespace}::{message_name}.{member}"
            decls: List[str] = []
            stmts: List[str] = []
            want_burst = has_burst and (signal.name, "_Pv") in watchable
            if want_burst:
                _append_burst_trigger_decls(decls, signal, "_Pv")
            if linkage_ok:
                _append_pv_to_rv_linkage_decls(decls)
            if want_burst:
                _append_burst_trigger_lines(
                    stmts, namespace, message_name, model, parsed, signal, "_Pv", member
                )
            if linkage_ok:
                _append_pv_to_rv_linkage_lines(stmts, namespace, message_name, signal)
            _append_apply_invoke(stmts, message_name, signal, "_Pv")
            if decls or stmts:
                lines.append(f"on sysvar {sv_path}")
                lines.append("{")
                lines.extend(decls)
                lines.extend(stmts)
                lines.append("}")
                lines.append("")

        if signal.has_rv:
            member = f"{signal.name}_Rv"
            sv_path = f"{namespace}::{message_name}.{member}"
            decls = []
            stmts = []
            want_burst = has_burst and (signal.name, "_Rv") in watchable
            if want_burst:
                _append_burst_trigger_decls(decls, signal, "_Rv")
            if linkage_ok:
                _append_rv_to_pv_linkage_decls(decls)
            if want_burst:
                _append_burst_trigger_lines(
                    stmts, namespace, message_name, model, parsed, signal, "_Rv", member
                )
            if linkage_ok:
                _append_rv_to_pv_linkage_lines(stmts, namespace, message_name, signal)
            if decls:
                lines.append(f"on sysvar {sv_path}")
                lines.append("{")
                lines.extend(decls)
                lines.extend(stmts)
                lines.append("}")
                lines.append("")

        if signal.has_special_value:
            member = f"{signal.name}_use_special_value"
            sv_path = f"{namespace}::{message_name}.{member}"
            decls = []
            stmts = []
            want_burst = has_burst and (signal.name, "_use_special_value") in watchable
            if want_burst:
                _append_burst_trigger_decls(decls, signal, "_use_special_value")
                _append_burst_trigger_lines(
                    stmts, namespace, message_name, model, parsed, signal, "_use_special_value", member
                )
            _append_apply_invoke(stmts, message_name, signal, "_use_special_value")
            if decls or stmts:
                lines.append(f"on sysvar {sv_path}")
                lines.append("{")
                lines.extend(decls)
                lines.extend(stmts)
                lines.append("}")
                lines.append("")

    return lines


def _build_msg_on_handler(
    namespace: str,
    message_name: str,
    model: MessageModel,
    parsed: ParsedSysvar,
    counter_signal: str = "",
    check_signal: str = "",
) -> List[str]:
    """MsgOn 控制周期 timer：开启 fill+sync+arm，关闭 cancelTimer。"""
    if not _needs_periodic_scheduler(model):
        return []
    if not _info_member_exists(parsed, message_name, "_MsgOn"):
        return []
    sv_path = f"{namespace}::{_info_var(message_name)}.{message_name}_MsgOn"
    msg_on = _info_sysvar(namespace, message_name, "_MsgOn", parsed, "1")
    lines = [
        f"on sysvar {sv_path}",
        "{",
        f"  if ({msg_on} == 1)",
        "  {",
    ]
    lines.extend(_build_startup_prepare_lines(message_name, model, counter_signal, check_signal, indent="    "))
    lines.append(f"    arm_{message_name}();")
    lines.extend([
        "  }",
        "  else",
        "  {",
        f"    cancelTimer(tmr_{message_name});",
        "  }",
        "}",
        "",
    ])
    return lines


def _build_on_start_arm_lines(
    namespace: str,
    message_name: str,
    model: MessageModel,
    parsed: ParsedSysvar,
) -> List[str]:
    if not _needs_periodic_scheduler(model):
        return []
    if _info_member_exists(parsed, message_name, "_MsgOn"):
        msg_on = _info_sysvar(namespace, message_name, "_MsgOn", parsed, "1")
        return [
            f"  if ({msg_on} == 1)",
            f"    arm_{message_name}();",
        ]
    return [f"  arm_{message_name}();"]


def _build_timer_variables(message_name: str) -> List[str]:
    return [
        f"  msTimer tmr_{message_name};",
        *_build_core_burst_timer_variables(message_name),
    ]


def _build_can_file(
    dbc_name: str,
    sender_node: str,
    channel: int,
    messages: List[Tuple[Dict[str, Any], MessageModel]],
    parsed: "ParsedSysvar",
    frame_ids: Optional[Dict[str, int]] = None,
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

    frame_ids = frame_ids or {}

    out.append("variables")
    out.append("{")
    for msg_cfg, model in messages:
        name = model.name
        frame_id = frame_ids.get(name)
        if frame_id is None and frame_ids:
            print(
                f"[capl_generator] 警告：DBC 中未找到报文 {name!r}，"
                f"将使用符号名声明 message（若编译失败请检查 DBC 或报文名）"
            )
        out.append(_message_decl(name, frame_id))
        out.extend(_build_timer_variables(name))
        if _counter_enabled(msg_cfg, model):
            out.append(f"  long cnt_{name};")
        exclude = set()
        if msg_cfg.get("has_validation", False):
            for key in ("check_signal", "counter_signal"):
                sig = msg_cfg.get(key, "")
                if sig:
                    exclude.add(sig)
        if _message_needs_quiet(model, exclude):
            out.append(f"  long {_quiet_var(name)};")
        if _needs_burst_support(model):
            out.extend(_build_burst_variables(name, model, exclude))
    out.append("}")
    out.append("")

    out.append("on start")
    out.append("{")
    for msg_cfg, model in messages:
        name = model.name
        out.append(f"  {_msg_var(name)}.CAN = {channel};")
        if _counter_enabled(msg_cfg, model):
            counter = model.get(msg_cfg.get("counter_signal", ""))
            cmin = _to_capl_number(counter.rv_min, "0")
            out.append(f"  cnt_{name} = {cmin};")
        exclude = set()
        if msg_cfg.get("has_validation", False):
            for key in ("check_signal", "counter_signal"):
                sig = msg_cfg.get(key, "")
                if sig:
                    exclude.add(sig)
        out.append(f"  burst_left_{name} = 0;")
        out.append(f"  burst_fast_{name} = 0;")
        if _needs_burst_support(model):
            if _is_mux_message(model):
                out.append(f"  {_burst_mux_var(name)} = -1;")
            for signal, suffix in _watchable_members(model, exclude):
                member = f"{signal.name}{suffix}"
                out.append(f"  {_restore_pending_var(name, member)} = 0;")
            out.extend(_build_init_shadows(namespace, name, model, exclude))
        if _message_needs_quiet(model, exclude):
            out.append(f"  {_quiet_var(name)} = 0;")
        counter_sig = msg_cfg.get("counter_signal", "") if msg_cfg.get("has_validation", False) else ""
        check_sig = msg_cfg.get("check_signal", "") if msg_cfg.get("has_validation", False) else ""
        out.extend(_build_startup_prepare_lines(name, model, counter_sig, check_sig))
        out.extend(_build_on_start_arm_lines(namespace, name, model, parsed))
    out.append("}")
    out.append("")

    for msg_cfg, model in messages:
        name = model.name
        exclude = set()
        if msg_cfg.get("has_validation", False):
            for key in ("check_signal", "counter_signal"):
                sig = msg_cfg.get(key, "")
                if sig:
                    exclude.add(sig)
        counter_sig = msg_cfg.get("counter_signal", "") if msg_cfg.get("has_validation", False) else ""
        check_sig = msg_cfg.get("check_signal", "") if msg_cfg.get("has_validation", False) else ""
        has_val = bool(msg_cfg.get("has_validation", False))
        if model.mux is not None:
            out.extend(
                _build_mux_output_all_groups_function(name, model, counter_sig, check_sig)
            )
        out.extend(
            _build_all_apply_functions(namespace, name, model, counter_sig, check_sig)
        )
        out.extend(_build_sync_payload_function(name, model, counter_sig, check_sig))
        out.extend(
            _build_refresh_crc_function(
                namespace,
                name,
                model,
                parsed,
                has_val,
                check_sig,
                msg_cfg.get("check_method", "crc16"),
                msg_cfg.get("check_parameters", {}),
            )
        )
        if _uses_begin_burst_send(model):
            out.extend(_build_begin_burst_function(namespace, name, parsed, model))
            out.extend(
                _build_finish_burst_function(
                    namespace, name, model, parsed, exclude, counter_sig, check_sig
                )
            )
        if _resolve_msg_send_type(model) == MSG_SEND_CE:
            out.extend(
                _build_send_additional_frame_function(
                    namespace, dbc_name, sender_node, name, model, parsed, has_val, counter_sig, check_sig
                )
            )
        out.extend(_build_arm_function(namespace, name, parsed, model))
        out.extend(
            _build_emit_function(namespace, dbc_name, sender_node, name, model, parsed)
        )
        out.extend(
            _build_timer_handler(
                namespace,
                dbc_name,
                sender_node,
                name,
                model,
                parsed,
                has_val,
                counter_sig,
                check_sig,
            )
        )
        out.extend(
            _build_send_function(
                namespace, dbc_name, sender_node, name, model, parsed, counter_sig, check_sig
            )
        )
        out.extend(
            _build_fill_function(
                namespace,
                name,
                model,
                parsed,
                bool(msg_cfg.get("has_validation", False)),
                msg_cfg.get("counter_signal", ""),
                msg_cfg.get("check_signal", ""),
                msg_cfg.get("check_method", "crc16"),
                msg_cfg.get("check_parameters", {}),
            )
        )
        out.extend(_build_merged_sysvar_handlers(namespace, name, model, parsed, exclude))
        out.extend(
            _build_msg_on_handler(namespace, name, model, parsed, counter_sig, check_sig)
        )

    return "\n".join(out) + "\n"


def _cycle_time_expr(namespace: str, message_name: str, parsed: ParsedSysvar) -> str:
    return _info_sysvar(namespace, message_name, "_MsgCycleTime", parsed, "10")


def _fast_cycle_time_expr(namespace: str, message_name: str, parsed: ParsedSysvar) -> str:
    cycle_expr = _cycle_time_expr(namespace, message_name, parsed)
    return _info_sysvar(namespace, message_name, "_MsgCycleTimeFast", parsed, cycle_expr)


def _append_arm_cycle_time_lines(
    lines: List[str],
    namespace: str,
    message_name: str,
    parsed: ParsedSysvar,
    model: MessageModel,
    *,
    use_fast: bool = False,
) -> None:
    if use_fast:
        cycle_expr = _fast_cycle_time_expr(namespace, message_name, parsed)
    else:
        cycle_expr = _cycle_time_expr(namespace, message_name, parsed)
    lines.append(f"  _ct = {cycle_expr};")
    lines.append("  if (_ct <= 0)")
    lines.append("    _ct = 10;")


def _build_arm_function(
    namespace: str,
    message_name: str,
    parsed: ParsedSysvar,
    model: MessageModel,
) -> List[str]:
    send_type = _resolve_msg_send_type(model)
    lines = [f"void arm_{message_name}()", "{", "  long _ct;"]
    if send_type in (MSG_SEND_EVENT, MSG_SEND_IF_ACTIVE):
        lines.extend([
            f"  if (burst_left_{message_name} <= 0)",
            "    return;",
        ])
    if _needs_burst_support(model):
        lines.extend([
            f"  if (burst_left_{message_name} > 0 && burst_fast_{message_name})",
            "  {",
        ])
        _append_arm_cycle_time_lines(
            lines, namespace, message_name, parsed, model, use_fast=True
        )
        lines.extend([
            "  }",
            "  else",
            "  {",
        ])
        _append_arm_cycle_time_lines(
            lines, namespace, message_name, parsed, model, use_fast=False
        )
        lines.extend([
            "  }",
        ])
    else:
        _append_arm_cycle_time_lines(
            lines, namespace, message_name, parsed, model, use_fast=False
        )
    lines.extend([
        f"  setTimer(tmr_{message_name}, _ct);",
        "}",
        "",
    ])
    return lines


def _build_emit_function(
    namespace: str,
    dbc_name: str,
    sender_node: str,
    message_name: str,
    model: MessageModel,
    parsed: ParsedSysvar,
) -> List[str]:
    msg = _msg_var(message_name)
    lines = [f"void emit_{message_name}()", "{"]
    _append_send_gate_lines(lines, namespace, dbc_name, sender_node, message_name, parsed)
    lines.append(f"  output({msg});")
    lines.append("}")
    lines.append("")
    return lines


def _build_send_additional_frame_function(
    namespace: str,
    dbc_name: str,
    sender_node: str,
    message_name: str,
    model: MessageModel,
    parsed: ParsedSysvar,
    has_validation: bool = False,
    counter_signal: str = "",
    check_signal: str = "",
) -> List[str]:
    """CE：OnChange/OnWrite 额外发一帧，不 cancelTimer、不改 burst_left；counter 同样叠加。"""
    msg = _msg_var(message_name)
    has_checksum = _message_has_checksum(has_validation, check_signal, model)
    if model.mux is not None:
        lines = [f"void send_additional_{message_name}(long mux_id)", "{"]
    else:
        lines = [f"void send_additional_{message_name}()", "{"]
    _append_send_gate_lines(lines, namespace, dbc_name, sender_node, message_name, parsed)
    if model.mux is not None:
        lines.append("  if (mux_id >= 0)")
        lines.append("  {")
        inner_indent = "    "
        if has_checksum:
            lines.append(f"{inner_indent}{_refresh_crc_function_name(message_name)}();")
        lines.extend(_build_fill_invoke_lines(message_name, model, indent=inner_indent))
        lines.extend(
            _build_sync_invoke_lines(
                message_name, model, counter_signal, check_signal, indent=inner_indent
            )
        )
        lines.append(f"{inner_indent}output({msg});")
        lines.extend(_build_fill_invoke_lines(message_name, model, indent=inner_indent))
        lines.extend(
            _build_sync_invoke_lines(
                message_name, model, counter_signal, check_signal, indent=inner_indent
            )
        )
        lines.append("  }")
    else:
        if has_checksum:
            lines.append(f"  {_refresh_crc_function_name(message_name)}();")
        lines.extend(_build_fill_invoke_lines(message_name, model, indent="  "))
        lines.extend(
            _build_sync_invoke_lines(
                message_name, model, counter_signal, check_signal, indent="  "
            )
        )
        lines.append(f"  output({msg});")
        lines.extend(_build_fill_invoke_lines(message_name, model, indent="  "))
        lines.extend(
            _build_sync_invoke_lines(
                message_name, model, counter_signal, check_signal, indent="  "
            )
        )
    lines.append("}")
    lines.append("")
    return lines


def _build_periodic_timer_cycle_lines(
    message_name: str,
    model: MessageModel,
    has_checksum: bool,
    counter_signal: str = "",
    check_signal: str = "",
    *,
    indent: str = "  ",
) -> List[str]:
    lines: List[str] = []
    if has_checksum:
        lines.append(f"{indent}{_refresh_crc_function_name(message_name)}();")
    lines.append(f"{indent}emit_{message_name}();")
    lines.extend(
        _build_prepare_invoke_lines(
            message_name, model, counter_signal, check_signal, indent=indent
        )
    )
    lines.append(f"{indent}arm_{message_name}();")
    return lines


def _build_timer_handler(
    namespace: str,
    dbc_name: str,
    sender_node: str,
    message_name: str,
    model: MessageModel,
    parsed: ParsedSysvar,
    has_validation: bool = False,
    counter_signal: str = "",
    check_signal: str = "",
) -> List[str]:
    has_checksum = _message_has_checksum(has_validation, check_signal, model)
    lines = [f"on timer tmr_{message_name}", "{"]
    if _uses_begin_burst_send(model):
        lines.extend([
            f"  if (burst_left_{message_name} > 0)",
            "  {",
            f"    send_{message_name}();",
            f"    burst_left_{message_name}--;",
            f"    if (burst_left_{message_name} <= 0)",
            f"      finish_burst_{message_name}();",
            "    else",
            f"      arm_{message_name}();",
            "  }",
            "  else",
            "  {",
        ])
        lines.extend(
            _build_periodic_timer_cycle_lines(
                message_name, model, has_checksum, counter_signal, check_signal, indent="    "
            )
        )
        lines.append("  }")
    else:
        lines.extend(
            _build_periodic_timer_cycle_lines(
                message_name, model, has_checksum, counter_signal, check_signal
            )
        )
    lines.extend(["}", ""])
    return lines


def _append_send_gate_lines(
    lines: List[str],
    namespace: str,
    dbc_name: str,
    sender_node: str,
    message_name: str,
    parsed: ParsedSysvar,
) -> None:
    info = _info_var(message_name)
    node_info = f"{dbc_name}_Node_Info"
    node_on = f"{dbc_name}_Node_On"
    if node_on in parsed.variable_names:
        lines.append(f"  if ({_sysvar(namespace, node_on)} != 1) return;")
    if f"{sender_node}_MsgOn" in parsed.member_names:
        lines.append(f"  if ({_sysvar(namespace, node_info, sender_node + '_MsgOn')} != 1) return;")
    if info in parsed.variable_names:
        lines.append(f"  if ({_sysvar(namespace, info, message_name + '_MsgOn')} != 1) return;")
        lines.append(f"  if ({_sysvar(namespace, info, message_name + '_MsgOff')} == 1) return;")


def _build_send_function(
    namespace: str,
    dbc_name: str,
    sender_node: str,
    message_name: str,
    model: MessageModel,
    parsed: "ParsedSysvar",
    counter_signal: str = "",
    check_signal: str = "",
) -> List[str]:
    msg = _msg_var(message_name)
    send_type = _resolve_msg_send_type(model)
    lines = [f"void send_{message_name}()", "{"]
    _append_send_gate_lines(lines, namespace, dbc_name, sender_node, message_name, parsed)

    if model.mux is not None:
        if _uses_begin_burst_send(model):
            burst_mux = _burst_mux_var(message_name)
            lines.append(f"  if (burst_left_{message_name} > 0)")
            lines.append("  {")
            if send_type in (MSG_SEND_CA,):
                lines.append(f"    output_all_{message_name}_groups();")
            else:
                lines.append(f"    if ({burst_mux} >= 0)")
                lines.append("    {")
                lines.append(f"      fill_{message_name}_group({burst_mux});")
                lines.extend(
                    _build_sync_invoke_lines(
                        message_name, model, counter_signal, check_signal, indent="      "
                    )
                )
                lines.append(f"      output({msg});")
                lines.append("    }")
            lines.append("    return;")
            lines.append("  }")
        lines.append(f"  output_all_{message_name}_groups();")
    else:
        lines.extend(_build_fill_invoke_lines(message_name, model, indent="  "))
        lines.extend(
            _build_sync_invoke_lines(
                message_name, model, counter_signal, check_signal, indent="  "
            )
        )
        lines.append(f"  output({msg});")
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
        frame_ids = load_message_frame_ids(dbc_path, project_path)

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

            content = _build_can_file(
                dbc_name, sender_node, channel, messages, parsed, frame_ids
            )
            file_path = output_dir / f"{dbc_name}_{sender_node}.can"
            file_path.write_text(content, encoding="utf-8")
            generated.append(str(file_path))

    return generated


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="根据系统变量(.vsysvar)为各发送节点生成 CANoe CAPL(.can) 文件"
    )
    parser.add_argument(
        "--project",
        required=True,
        help=r"项目根目录，例如 D:\Test\case_editor\projects\proj1",
    )
    parser.add_argument(
        "--config",
        help="config 的 JSON 文件路径（内容为传给 generate_capl 的 config 字典）",
    )
    parser.add_argument(
        "--sysvar",
        help="可选：直接指定 .vsysvar 路径，覆盖 config 里的 selected_system_variable_file",
    )
    args = parser.parse_args()

    # 读取 config：优先用 --config 指定的 JSON 文件，否则构造一个仅含系统变量文件的空配置。
    if args.config:
        with open(args.config, "r", encoding="utf-8") as fh:
            run_config: Dict[str, Any] = json.load(fh)
    else:
        run_config = {"dbc_configs": [], "selected_system_variable_file": args.sysvar or ""}

    if args.sysvar:
        run_config["selected_system_variable_file"] = args.sysvar

    generated_files = generate_capl(run_config, args.project)
    print(f"共生成 {len(generated_files)} 个 .can 文件：")
    for generated_file in generated_files:
        print("  ", generated_file)
