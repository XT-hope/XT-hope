#!/usr/bin/env python3
"""
根据 DBC 文件生成 CANoe 系统变量 XML（可导入 CANoe）。

设计目标：
- 可靠解析：使用 cantools 解析 DBC
- 可配置：命名空间、变量命名规则、输出格式
- 可测试：提供示例 DBC 与一键命令

注意：
- Vector CANoe/Toolchain 对“系统变量 XML”的具体 schema 会随版本变化。
  本脚本默认输出一种常见的“vsysvar 风格”结构，并额外提供 generic XML 作为兜底。
  若你的 CANoe 导入提示 schema 不匹配，可用 --format generic 或按你版本导出的样例微调标签名/属性。
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as _dt
import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable, Literal


try:
    import cantools  # type: ignore
except Exception as e:  # pragma: no cover
    raise SystemExit(
        "缺少依赖 cantools。请先安装：\n"
        "  python3 -m pip install -r requirements.txt\n"
        f"原始错误: {e}"
    )


SysVarType = Literal["bool", "int", "uint", "double", "string"]


@dataclasses.dataclass(frozen=True)
class SysVar:
    namespace: tuple[str, ...]  # 例如 ("DBC", "MsgName")
    name: str  # 变量名（不含 namespace）
    var_type: SysVarType
    initial: str
    minimum: str | None
    maximum: str | None
    unit: str | None
    comment: str | None

    @property
    def full_path(self) -> str:
        # 使用 :: 连接，便于人阅读；XML 内部用分层 namespace 表达
        return "::".join((*self.namespace, self.name))


_IDENT_RE = re.compile(r"[^A-Za-z0-9_]")


def sanitize_identifier(name: str, *, fallback: str = "VAR") -> str:
    """将任意字符串转成较安全的标识符（CANoe/多数 XML schema 常见要求）。"""
    name = name.strip()
    if not name:
        return fallback
    name = _IDENT_RE.sub("_", name)
    if name[0].isdigit():
        name = f"_{name}"
    # 避免连续下划线太多
    name = re.sub(r"_+", "_", name)
    return name


def _is_effectively_integer_signal(sig) -> bool:
    """
    cantools.Signal:
      - is_float: True 表示 IEEE float/double 类型信号（DBC 支持）
      - 其它常见情况：整数信号 + (scale, offset)
    这里尽量推断“最终物理量”是否是整数。
    """
    if getattr(sig, "is_float", False):
        return False
    scale = getattr(sig, "scale", 1) or 1
    offset = getattr(sig, "offset", 0) or 0
    # scale/offset 只要不是整数，就认为物理量可能是浮点
    if not float(scale).is_integer():
        return False
    if not float(offset).is_integer():
        return False
    return True


def infer_sysvar_type(sig) -> SysVarType:
    """把 DBC Signal 映射为系统变量类型。"""
    if getattr(sig, "choices", None):
        # 枚举：通常用整型承载
        return "int" if getattr(sig, "is_signed", False) else "uint"
    if getattr(sig, "length", 0) == 1:
        return "bool"
    if not _is_effectively_integer_signal(sig):
        return "double"
    return "int" if getattr(sig, "is_signed", False) else "uint"


def _fmt_num(x: float | int | None) -> str | None:
    if x is None:
        return None
    if isinstance(x, bool):  # bool 是 int 子类，需提前处理
        return "1" if x else "0"
    if isinstance(x, int):
        return str(x)
    if isinstance(x, float):
        if math.isnan(x) or math.isinf(x):
            return None
        # 保持尽量短且可读
        if x.is_integer():
            return str(int(x))
        return format(x, ".15g")
    return str(x)


def _infer_min_max(sig) -> tuple[str | None, str | None]:
    """
    取 DBC 的物理量 min/max（如果存在）。
    cantools 的 minimum/maximum 通常就是物理值（已应用 scale/offset）。
    """
    mn = _fmt_num(getattr(sig, "minimum", None))
    mx = _fmt_num(getattr(sig, "maximum", None))
    return mn, mx


def _infer_initial_value(sig, var_type: SysVarType) -> str:
    # DBC 通常没有“初始值”，这里给一个安全默认
    if var_type == "bool":
        return "0"
    if var_type in ("int", "uint"):
        return "0"
    if var_type == "double":
        return "0"
    if var_type == "string":
        return ""
    return "0"


def build_sysvars_from_dbc(
    dbc_path: Path,
    *,
    root_namespace: str,
    group_by_message: bool,
    name_pattern: str,
    include_extended_comment: bool,
) -> list[SysVar]:
    """
    从 DBC 生成 SysVar 列表。

    name_pattern 支持占位符：
    - {message}: message 名
    - {signal}: signal 名
    - {frame_id}: message 帧 ID（十进制）
    """
    db = cantools.database.load_file(str(dbc_path))
    sysvars: list[SysVar] = []

    for msg in db.messages:
        msg_name = sanitize_identifier(msg.name, fallback="MSG")
        frame_id = getattr(msg, "frame_id", None)
        frame_id_str = str(int(frame_id)) if frame_id is not None else "0"
        msg_ns = (sanitize_identifier(root_namespace, fallback="DBC"),)
        if group_by_message:
            msg_ns = (*msg_ns, msg_name)

        for sig in msg.signals:
            sig_name = sanitize_identifier(sig.name, fallback="SIG")
            var_name_raw = name_pattern.format(message=msg_name, signal=sig_name, frame_id=frame_id_str)
            var_name = sanitize_identifier(var_name_raw, fallback=f"{msg_name}_{sig_name}")

            var_type = infer_sysvar_type(sig)
            mn, mx = _infer_min_max(sig)
            unit = getattr(sig, "unit", None) or None

            comment_parts: list[str] = []
            sig_comment = getattr(sig, "comment", None)
            if sig_comment:
                comment_parts.append(str(sig_comment).strip())

            if include_extended_comment and getattr(sig, "choices", None):
                # 把枚举信息写进 comment，便于在 CANoe 中查看
                choices = getattr(sig, "choices", {})
                # choices 可能是 dict[int,str]
                items = sorted(choices.items(), key=lambda kv: kv[0])
                enum_str = ", ".join([f"{k}={v}" for k, v in items])
                if enum_str:
                    comment_parts.append(f"choices: {enum_str}")

            # 额外加上 DBC message 信息，便于溯源
            if include_extended_comment:
                msg_comment = getattr(msg, "comment", None)
                if msg_comment:
                    comment_parts.append(f"messageComment: {str(msg_comment).strip()}")
                comment_parts.append(f"dbc: {dbc_path.name}, frame_id: {frame_id_str}")

            comment = "\n".join([p for p in comment_parts if p]) or None
            initial = _infer_initial_value(sig, var_type)

            sysvars.append(
                SysVar(
                    namespace=msg_ns,
                    name=var_name,
                    var_type=var_type,
                    initial=initial,
                    minimum=mn,
                    maximum=mx,
                    unit=unit,
                    comment=comment,
                )
            )

    # 稳定排序，便于 diff / 版本管理
    sysvars.sort(key=lambda v: (v.namespace, v.name))
    return sysvars


def _indent(elem: ET.Element, level: int = 0) -> None:
    """Python 3.12 的 ElementTree 不保证漂亮缩进，手工缩进便于阅读。"""
    i = "\n" + level * "  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        for child in elem:
            _indent(child, level + 1)
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i


def _ensure_namespace_tree(root: ET.Element, namespace: tuple[str, ...]) -> ET.Element:
    """
    在 vsysvar 风格 XML 中创建/复用分层 namespace 节点。
    结构示例：
      <Namespace name="DBC">
        <Namespace name="MsgA">
          <Variable ... />
        </Namespace>
      </Namespace>
    """
    current = root
    for ns in namespace:
        found = None
        for child in current:
            if child.tag == "Namespace" and child.get("name") == ns:
                found = child
                break
        if found is None:
            found = ET.SubElement(current, "Namespace", {"name": ns})
        current = found
    return current


def write_vector_vsysvar_xml(sysvars: Iterable[SysVar], out_path: Path) -> None:
    """
    输出一种常见“vsysvar 风格”结构（标签名：SystemVariables/Namespace/Variable）。
    这不是官方 schema 的逐字复制，但在很多 Vector 工具链里是接近的层级组织方式。
    """
    root = ET.Element(
        "SystemVariables",
        {
            "generator": "dbc_to_canoe_sysvars.py",
            "generatedAt": _dt.datetime.now().isoformat(timespec="seconds"),
        },
    )

    for v in sysvars:
        ns_node = _ensure_namespace_tree(root, v.namespace)
        attrs: dict[str, str] = {
            "name": v.name,
            "type": v.var_type,
            "initial": v.initial,
        }
        if v.minimum is not None:
            attrs["min"] = v.minimum
        if v.maximum is not None:
            attrs["max"] = v.maximum
        if v.unit:
            attrs["unit"] = v.unit

        var_node = ET.SubElement(ns_node, "Variable", attrs)
        if v.comment:
            c = ET.SubElement(var_node, "Comment")
            c.text = v.comment

    _indent(root)
    tree = ET.ElementTree(root)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(out_path, encoding="utf-8", xml_declaration=True)


def write_generic_xml(sysvars: Iterable[SysVar], out_path: Path) -> None:
    """输出一个完全自描述的通用 XML（不依赖任何 Vector schema 约定）。"""
    root = ET.Element(
        "dbcSystemVariables",
        {
            "generator": "dbc_to_canoe_sysvars.py",
            "generatedAt": _dt.datetime.now().isoformat(timespec="seconds"),
        },
    )
    for v in sysvars:
        attrs: dict[str, str] = {
            "path": v.full_path,
            "type": v.var_type,
            "initial": v.initial,
        }
        if v.minimum is not None:
            attrs["min"] = v.minimum
        if v.maximum is not None:
            attrs["max"] = v.maximum
        if v.unit:
            attrs["unit"] = v.unit
        e = ET.SubElement(root, "var", attrs)
        if v.comment:
            e.text = v.comment
    _indent(root)
    tree = ET.ElementTree(root)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(out_path, encoding="utf-8", xml_declaration=True)


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="根据 DBC 文件自动生成 CANoe 系统变量 XML（可导入 CANoe）"
    )
    p.add_argument("--dbc", required=True, help="输入 DBC 文件路径")
    p.add_argument(
        "--out",
        required=True,
        help="输出 XML 路径（建议后缀 .vsysvar 或 .xml）",
    )
    p.add_argument(
        "--root-namespace",
        default="DBC",
        help="根命名空间（默认：DBC）",
    )
    p.add_argument(
        "--no-group-by-message",
        action="store_true",
        help="不按 Message 分组（默认按 message 分组：DBC/<Message>/<Signal>）",
    )
    p.add_argument(
        "--name-pattern",
        default="{signal}",
        help="变量名模式（默认：{signal}；可用 {message} {signal} {frame_id}）",
    )
    p.add_argument(
        "--format",
        default="vector-vsysvar",
        choices=["vector-vsysvar", "generic"],
        help="输出格式：vector-vsysvar 或 generic",
    )
    p.add_argument(
        "--no-extended-comment",
        action="store_true",
        help="不输出扩展注释（choices/messageComment/frame_id 等）",
    )
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    dbc_path = Path(args.dbc).expanduser().resolve()
    out_path = Path(args.out).expanduser().resolve()

    if not dbc_path.exists():
        print(f"错误：DBC 不存在：{dbc_path}", file=sys.stderr)
        return 2

    sysvars = build_sysvars_from_dbc(
        dbc_path,
        root_namespace=args.root_namespace,
        group_by_message=(not args.no_group_by_message),
        name_pattern=args.name_pattern,
        include_extended_comment=(not args.no_extended_comment),
    )

    if args.format == "vector-vsysvar":
        write_vector_vsysvar_xml(sysvars, out_path)
    else:
        write_generic_xml(sysvars, out_path)

    print(f"已生成 {len(sysvars)} 个系统变量：{out_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))

