from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from xml.etree import ElementTree as ET

import cantools


@dataclass
class ValueTableEntry:
	value: Decimal
	description: str


@dataclass
class MessageInfo:
	send_type_value: Decimal
	send_type_name: str
	send_type_choices: List[ValueTableEntry]
	cycle_time: Decimal
	cycle_time_max: Optional[Decimal] = None


@dataclass
class DbcSignal:
	name: str
	start_bit: int
	length: int
	byte_order: int
	is_signed: bool
	factor: Decimal
	offset: Decimal
	minimum: Decimal
	maximum: Decimal
	unit: str
	receivers: List[str]
	comment: str = ""
	start_raw: Decimal = Decimal("0")
	choices: List[ValueTableEntry] = field(default_factory=list)


@dataclass
class DbcMessage:
	frame_id: int
	name: str
	dlc: int
	sender: str
	info: MessageInfo
	signals: List[DbcSignal] = field(default_factory=list)


@dataclass
class DbcDatabase:
	messages: List[DbcMessage]


def read_text_file(path: str, encoding: Optional[str] = None) -> str:
	"""Read DBC text while tolerating common Chinese and UTF encodings."""
	with open(path, "rb") as fh:
		data = fh.read()

	return decode_dbc_bytes(data, preferred_encoding=encoding)


def decode_dbc_bytes(data: bytes, preferred_encoding: Optional[str] = None) -> str:
	encoding = preferred_encoding or "utf-8-sig"
	return data.decode(encoding)


def parse_dbc_file(path: str, encoding: Optional[str] = None) -> DbcDatabase:
	return parse_dbc_text(read_text_file(path, encoding=encoding))


def parse_dbc_text(text: str) -> DbcDatabase:
	database = cantools.database.load_string(
		text,
		database_format="dbc",
		strict=False,
		sort_signals=None,
	)
	return DbcDatabase(messages=[convert_cantools_message(message) for message in database.messages])


def convert_cantools_message(message) -> DbcMessage:
	senders = getattr(message, "senders", None) or []
	return DbcMessage(
		frame_id=message.frame_id,
		name=message.name,
		dlc=message.length,
		sender=senders[0] if senders else "",
		info=convert_cantools_message_info(message),
		signals=[convert_cantools_signal(signal) for signal in message.signals],
	)


def convert_cantools_message_info(message) -> MessageInfo:
	send_type_choices = get_attribute_choices(message, "GenMsgSendType") or default_send_type_choices()
	send_type_value = get_message_attribute_value(message, "GenMsgSendType")
	if send_type_value is None:
		send_type_value = get_attribute_default_value(message, "GenMsgSendType")
	send_type_index = resolve_send_type_index(send_type_value, send_type_choices)
	cycle_time = get_message_attribute_value(message, "GenMsgCycleTime")
	if cycle_time is None:
		cycle_time = get_attribute_default_value(message, "GenMsgCycleTime")

	return MessageInfo(
		send_type_value=send_type_index,
		send_type_name=choice_name_by_value(send_type_choices, send_type_index),
		send_type_choices=send_type_choices,
		cycle_time=to_decimal(cycle_time, Decimal("0")),
		cycle_time_max=get_attribute_maximum(message, "GenMsgCycleTime"),
	)


def convert_cantools_signal(signal) -> DbcSignal:
	return DbcSignal(
		name=signal.name,
		start_bit=signal.start,
		length=signal.length,
		byte_order=1 if signal.byte_order == "little_endian" else 0,
		is_signed=signal.is_signed,
		factor=to_decimal(signal.scale, Decimal("1")),
		offset=to_decimal(signal.offset, Decimal("0")),
		minimum=to_decimal(signal.minimum, Decimal("0")),
		maximum=to_decimal(signal.maximum, Decimal("0")),
		unit=signal.unit or "",
		receivers=list(signal.receivers),
		comment=signal.comment or "",
		start_raw=to_decimal(signal.raw_initial, Decimal("0")),
		choices=convert_cantools_choices(signal.choices),
	)


def convert_cantools_choices(choices) -> List[ValueTableEntry]:
	if not choices:
		return []

	entries: List[ValueTableEntry] = []
	for value, description in choices.items():
		entries.append(
			ValueTableEntry(
				value=to_decimal(value, Decimal("0")),
				description=str(description),
			)
		)
	return sorted(entries, key=lambda entry: entry.value)


def default_send_type_choices() -> List[ValueTableEntry]:
	return [
		ValueTableEntry(Decimal(index), name)
		for index, name in enumerate(["Cycle", "Event", "IfActive", "CE", "CA", "NoMsgSendType"])
	]


def get_message_attribute_value(message, name: str):
	attribute = getattr(message.dbc, "_attributes", {}).get(name) if message.dbc else None
	return getattr(attribute, "value", None) if attribute is not None else None


def get_attribute_definition(message, name: str):
	return getattr(message.dbc, "_attribute_definitions", {}).get(name) if message.dbc else None


def get_attribute_default_value(message, name: str):
	definition = get_attribute_definition(message, name)
	return getattr(definition, "default_value", None) if definition is not None else None


def get_attribute_maximum(message, name: str) -> Optional[Decimal]:
	definition = get_attribute_definition(message, name)
	if definition is None:
		return None
	return to_optional_decimal(getattr(definition, "maximum", None))


def get_attribute_choices(message, name: str) -> List[ValueTableEntry]:
	definition = get_attribute_definition(message, name)
	choices = getattr(definition, "choices", None) if definition is not None else None
	if not choices:
		return []
	return [ValueTableEntry(Decimal(index), str(choice)) for index, choice in enumerate(choices)]


def resolve_send_type_index(value, choices: List[ValueTableEntry]) -> Decimal:
	if value is None:
		value = "Cycle"
	if isinstance(value, str):
		for entry in choices:
			if entry.description == value:
				return entry.value
		return Decimal("0")
	return to_decimal(value, Decimal("0"))


def choice_name_by_value(choices: List[ValueTableEntry], value: Decimal) -> str:
	for entry in choices:
		if entry.value == value:
			return entry.description
	return "Cycle"


def to_decimal(value, default: Decimal) -> Decimal:
	if value is None:
		return default
	return Decimal(str(value))


def to_optional_decimal(value) -> Optional[Decimal]:
	if value is None:
		return None
	return Decimal(str(value))


def decimal_to_text(value: Decimal) -> str:
	if value.is_zero():
		return "0"
	normalized = value.normalize()
	text = format(normalized, "f")
	if "." in text:
		text = text.rstrip("0").rstrip(".")
	return text or "0"


def physical_start_value(signal: DbcSignal) -> Decimal:
	return signal.start_raw * signal.factor + signal.offset


def raw_range_from_physical(signal: DbcSignal) -> Tuple[Decimal, Decimal]:
	if signal.factor == 0:
		return Decimal("0"), Decimal("0")

	raw_a = (signal.minimum - signal.offset) / signal.factor
	raw_b = (signal.maximum - signal.offset) / signal.factor
	low = min(raw_a, raw_b)
	high = max(raw_a, raw_b)

	return (
		low.to_integral_value(rounding=ROUND_CEILING),
		high.to_integral_value(rounding=ROUND_FLOOR),
	)


def build_vsysvar_tree(dbc_specs: Sequence[Tuple[str, DbcDatabase]]) -> ET.ElementTree:
	root = ET.Element("systemvariables", {"version": "4"})
	root_namespace = ET.SubElement(root, "namespace", namespace_attrs(""))

	for namespace_name, database in dbc_specs:
		namespace_element = ET.SubElement(root_namespace, "namespace", namespace_attrs(namespace_name))
		for message in database.messages:
			add_message_info_struct_and_variable(namespace_element, namespace_name, message)
			add_message_struct_and_variable(namespace_element, namespace_name, message)

	tree = ET.ElementTree(root)
	ET.indent(tree, space="  ")
	return tree


def namespace_attrs(name: str) -> Dict[str, str]:
	return {"name": name, "comment": "", "interface": ""}


def add_message_info_struct_and_variable(
	namespace_element: ET.Element, namespace_name: str, message: DbcMessage
) -> None:
	struct_name = f"{message.name.lower()}_info"
	struct_element = ET.SubElement(
		namespace_element,
		"struct",
		{
			"name": struct_name,
			"isUnion": "False",
			"definedBinaryLayout": "False",
			"comment": "",
		},
	)

	member_count = 0
	for name, start_value, min_value, max_value, choices in message_info_member_specs(message):
		member_element = ET.SubElement(
			struct_element,
			"structMember",
			struct_member_attrs(
				name=name,
				comment="",
				is_signed=False,
				member_type="int",
				start_value=start_value,
				min_value=min_value,
				max_value=max_value,
				bitcount=32,
			),
		)
		if choices:
			add_value_table(member_element, f"{name}Vt", choices)
		member_count += 1

	ET.SubElement(
		namespace_element,
		"variable",
		{
			"anlyzLocal": "2",
			"readOnly": "false",
			"valueSequence": "false",
			"unit": "",
			"name": f"{message.name}_Info",
			"comment": "",
			"bitcount": str(member_count * 32),
			"isSigned": "true",
			"encoding": "65001",
			"type": "struct",
			"structDefinition": f"{namespace_name}::{struct_name}",
		},
	)


def message_info_member_specs(
	message: DbcMessage,
) -> Iterable[Tuple[str, Decimal, Optional[Decimal], Optional[Decimal], List[ValueTableEntry]]]:
	prefix = message.name
	send_type_max = Decimal(len(message.info.send_type_choices) - 1)
	specs = [
		(f"{prefix}_MsgOn", Decimal("1"), Decimal("0"), Decimal("1"), []),
		(f"{prefix}_MsgOff", Decimal("0"), Decimal("0"), Decimal("1"), []),
		(
			f"{prefix}_MsgSendType",
			message.info.send_type_value,
			Decimal("0"),
			send_type_max,
			message.info.send_type_choices,
		),
	]
	if message.info.send_type_name in {"Cycle", "CE", "CA"}:
		specs.append(
			(
				f"{prefix}_MsgCycleTime",
				message.info.cycle_time,
				Decimal("0"),
				message.info.cycle_time_max,
				[],
			)
		)
	return specs


def add_message_struct_and_variable(
	namespace_element: ET.Element, namespace_name: str, message: DbcMessage
) -> None:
	struct_name = message.name.lower()
	struct_element = ET.SubElement(
		namespace_element,
		"struct",
		{
			"name": struct_name,
			"isUnion": "False",
			"definedBinaryLayout": "False",
			"comment": "",
		},
	)

	bitcount = 0
	for signal in message.signals:
		for suffix, member_type, start_value, min_value, max_value, include_value_table in signal_member_specs(signal):
			member_element = ET.SubElement(
				struct_element,
				"structMember",
				struct_member_attrs(
					name=f"{signal.name}_{suffix}",
					comment=signal.comment,
					is_signed=signal.is_signed,
					member_type=member_type,
					start_value=start_value,
					min_value=min_value,
					max_value=max_value,
				),
			)
			if include_value_table and signal.choices:
				add_value_table(member_element, f"{signal.name}Vt", signal.choices)
			bitcount += 64

	ET.SubElement(
		namespace_element,
		"variable",
		{
			"anlyzLocal": "2",
			"readOnly": "false",
			"valueSequence": "false",
			"unit": "",
			"name": message.name,
			"comment": "",
			"bitcount": str(bitcount),
			"isSigned": "true",
			"encoding": "65001",
			"type": "struct",
			"structDefinition": f"{namespace_name}::{struct_name}",
		},
	)


def signal_member_specs(
	signal: DbcSignal,
) -> Iterable[Tuple[str, str, Decimal, Optional[Decimal], Optional[Decimal], bool]]:
	raw_min, raw_max = raw_range_from_physical(signal)
	value_member_type = "int" if signal.choices else "double"
	return (
		("Pv", value_member_type, physical_start_value(signal), signal.minimum, signal.maximum, True),
		("Rv", "int", signal.start_raw, raw_min, raw_max, True),
		("Factor", "double", signal.factor, None, None, False),
		("Offset", "double", signal.offset, None, None, False),
	)


def struct_member_attrs(
	name: str,
	comment: str,
	is_signed: bool,
	member_type: str,
	start_value: Decimal,
	min_value: Optional[Decimal],
	max_value: Optional[Decimal],
	bitcount: int = 64,
) -> Dict[str, str]:
	attrs = {
		"relativeOffset": "0",
		"byteOrder": "0",
		"isOptional": "False",
		"isHidden": "False",
		"name": name,
		"comment": comment,
		"bitcount": str(bitcount),
		"isSigned": "true" if is_signed else "false",
		"encoding": "65001",
		"type": member_type,
		"startValue": decimal_to_text(start_value),
	}
	if min_value is not None:
		attrs["minValue"] = decimal_to_text(min_value)
	if max_value is not None:
		attrs["maxValue"] = decimal_to_text(max_value)
	return attrs


def add_value_table(
	member_element: ET.Element, value_table_name: str, entries: List[ValueTableEntry]
) -> None:
	value_table = ET.SubElement(
		member_element,
		"valuetable",
		{
			"name": value_table_name,
			"definesMinMax": "false",
		},
	)
	for entry in entries:
		value = decimal_to_text(entry.value)
		ET.SubElement(
			value_table,
			"valuetableentry",
			{
				"value": value,
				"lowerBound": value,
				"upperBound": value,
				"description": entry.description,
				"displayString": entry.description,
			},
		)


def write_vsysvar_file(tree: ET.ElementTree, output_path: str) -> None:
	output_dir = os.path.dirname(output_path)
	if output_dir:
		os.makedirs(output_dir, exist_ok=True)
	tree.write(output_path, encoding="utf-8", xml_declaration=True)


def parse_dbc_spec(spec: str) -> Tuple[str, str]:
	if "=" in spec:
		namespace, path = spec.split("=", 1)
		namespace = namespace.strip()
		path = path.strip()
		if not namespace or not path:
			raise ValueError(f"Invalid DBC spec '{spec}'. Expected Namespace=path/to/file.dbc")
		return namespace, path

	path = spec.strip()
	if not path:
		raise ValueError("DBC path must not be empty")
	return derive_namespace_from_path(path), path


def derive_namespace_from_path(path: str) -> str:
	name = os.path.splitext(os.path.basename(path))[0]
	name = re.sub(r"[^0-9A-Za-z_]+", "_", name).strip("_")
	return name or "DBC"


def convert_dbc_files_to_vsysvar(
	dbc_specs: Sequence[Tuple[str, str]], output_path: str, encoding: Optional[str] = None
) -> None:
	databases = [(namespace, parse_dbc_file(path, encoding=encoding)) for namespace, path in dbc_specs]
	tree = build_vsysvar_tree(databases)
	write_vsysvar_file(tree, output_path)


def main(argv: Optional[Sequence[str]] = None) -> None:
	parser = argparse.ArgumentParser(
		description="Convert one or more DBC files to a CANoe .vsysvar system variable file."
	)
	parser.add_argument(
		"--dbc",
		action="append",
		required=True,
		help="DBC input. Use Namespace=path/to/file.dbc; may be repeated.",
	)
	parser.add_argument("--out", required=True, help="Output .vsysvar path")
	parser.add_argument(
		"--dbc-encoding",
		help="Optional DBC file encoding, for example gb18030 for GBK/ANSI Chinese DBC files.",
	)
	args = parser.parse_args(argv)

	convert_dbc_files_to_vsysvar(
		[parse_dbc_spec(spec) for spec in args.dbc],
		args.out,
		encoding=args.dbc_encoding,
	)


if __name__ == "__main__":
	main()
