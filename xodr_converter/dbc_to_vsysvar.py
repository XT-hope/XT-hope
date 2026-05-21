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


@dataclass
class DbcMessage:
	frame_id: int
	name: str
	dlc: int
	sender: str
	signals: List[DbcSignal] = field(default_factory=list)


@dataclass
class DbcDatabase:
	messages: List[DbcMessage]


def read_text_file(path: str) -> str:
	"""Read DBC text while tolerating common Chinese and UTF encodings."""
	with open(path, "rb") as fh:
		data = fh.read()

	for encoding in ("utf-8-sig", "utf-8", "gb18030", "cp1252"):
		try:
			return data.decode(encoding)
		except UnicodeDecodeError:
			continue
	return data.decode("utf-8", errors="replace")


def parse_dbc_file(path: str) -> DbcDatabase:
	return parse_dbc_text(read_text_file(path))


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
		signals=[convert_cantools_signal(signal) for signal in message.signals],
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
	)


def to_decimal(value, default: Decimal) -> Decimal:
	if value is None:
		return default
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
			add_message_struct_and_variable(namespace_element, namespace_name, message)

	tree = ET.ElementTree(root)
	ET.indent(tree, space="  ")
	return tree


def namespace_attrs(name: str) -> Dict[str, str]:
	return {"name": name, "comment": "", "interface": ""}


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
		for suffix, member_type, start_value, min_value, max_value in signal_member_specs(signal):
			ET.SubElement(
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
) -> Iterable[Tuple[str, str, Decimal, Optional[Decimal], Optional[Decimal]]]:
	raw_min, raw_max = raw_range_from_physical(signal)
	return (
		("Pv", "double", physical_start_value(signal), signal.minimum, signal.maximum),
		("Rv", "int", signal.start_raw, raw_min, raw_max),
		("Factor", "double", signal.factor, None, None),
		("Offset", "double", signal.offset, None, None),
	)


def struct_member_attrs(
	name: str,
	comment: str,
	is_signed: bool,
	member_type: str,
	start_value: Decimal,
	min_value: Optional[Decimal],
	max_value: Optional[Decimal],
) -> Dict[str, str]:
	attrs = {
		"relativeOffset": "0",
		"byteOrder": "0",
		"isOptional": "False",
		"isHidden": "False",
		"name": name,
		"comment": comment,
		"bitcount": "64",
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


def convert_dbc_files_to_vsysvar(dbc_specs: Sequence[Tuple[str, str]], output_path: str) -> None:
	databases = [(namespace, parse_dbc_file(path)) for namespace, path in dbc_specs]
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
	args = parser.parse_args(argv)

	convert_dbc_files_to_vsysvar([parse_dbc_spec(spec) for spec in args.dbc], args.out)


if __name__ == "__main__":
	main()
