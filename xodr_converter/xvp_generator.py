from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence
from xml.etree import ElementTree as ET


PANEL_TYPE = "Vector.CANalyzer.Panels.PanelSerializer, Vector.CANalyzer.Panels.Serializer, Version=18.0.150.0, Culture=neutral, PublicKeyToken=null"
RUNTIME_PANEL_TYPE = "Vector.CANalyzer.Panels.Runtime.Panel, Vector.CANalyzer.Panels.Common, Version=18.0.150.0, Culture=neutral, PublicKeyToken=null"
GROUP_BOX_TYPE = "Vector.CANalyzer.Panels.Design.GroupBoxControl, Vector.CANalyzer.Panels.CommonControls, Version=18.0.150.0, Culture=neutral, PublicKeyToken=null"
STATIC_TEXT_TYPE = "Vector.CANalyzer.Panels.Design.StaticTextControl, Vector.CANalyzer.Panels.CommonControls, Version=18.0.150.0, Culture=neutral, PublicKeyToken=null"
TEXT_BOX_TYPE = "Vector.CANalyzer.Panels.Design.TextBoxControl, Vector.CANalyzer.Panels.CommonControls, Version=18.0.150.0, Culture=neutral, PublicKeyToken=null"
COMBO_BOX_TYPE = "Vector.CANalyzer.Panels.Design.ComboBoxControl, Vector.CANalyzer.Panels.CommonControls, Version=18.0.150.0, Culture=neutral, PublicKeyToken=null"
RADIO_BUTTON_TYPE = "Vector.CANalyzer.Panels.Design.RadioButtonControl, Vector.CANalyzer.Panels.CommonControls, Version=18.0.150.0, Culture=neutral, PublicKeyToken=null"
CANVAS_TYPE = "Vector.CANalyzer.Panels.Design.CanvasControl, Vector.CANalyzer.Panels.CommonControls, Version=18.0.150.0, Culture=neutral, PublicKeyToken=null"

GROUP_WIDTH = 1160
PANEL_WIDTH = 1170
SIGNAL_RAW_SEPARATOR_X = 211
RAW_PHYSICAL_SEPARATOR_X = 485
PHYSICAL_SPECIAL_SEPARATOR_X = 930
RAW_VALUE_CONTROL_X = 256
RAW_MIN_MAX_X = 385
RAW_TEXT_BOX_WIDTH = 120
DEFAULT_VALUE_CONTROL_WIDTH = 187
PHYSICAL_VALUE_CONTROL_X = 533
PHYSICAL_MIN_MAX_X = 787
SPECIAL_VALUE_X = 945
INACTIVE_VALUE_X = 1050
MIN_MAX_FONT = "Microsoft Sans Serif, 9.25pt"
DEFAULT_LOWER_LIMIT = "-2147483648"
DEFAULT_UPPER_LIMIT = "2147483647"


@dataclass
class StructMemberInfo:
	name: str
	member_type: str
	comment: str = ""
	min_value: str = "~"
	max_value: str = "~"
	valuetable: Dict[str, str] = field(default_factory=dict)


@dataclass
class MessageInfo:
	namespace: str
	variable_name: str
	struct_name: str
	members: Dict[str, StructMemberInfo]


@dataclass
class SignalRow:
	name: str
	raw_member: StructMemberInfo
	physical_member: StructMemberInfo
	use_special_member: Optional[StructMemberInfo] = None
	use_inactive_member: Optional[StructMemberInfo] = None


def generation_xvp(sysvar_path: str, selected_variables: Dict[str, List[str]], output_dir: str) -> List[str]:
	"""
	生成 CANoe 面板文件(.xvp)。

	Args:
		sysvar_path: 系统变量文件完整路径。
		selected_variables: {"namespace": ["MessageName", ...]}。
		output_dir: 输出目录完整路径。

	Returns:
		生成的 .xvp 文件路径列表。每个选中的 message 会生成一个独立文件。
	"""
	messages = parse_selected_messages(sysvar_path, selected_variables)
	os.makedirs(output_dir, exist_ok=True)

	output_paths: List[str] = []
	for message in messages:
		panel_tree = build_panel_tree([message])
		output_name = panel_file_name(sysvar_path, message)
		output_path = str(Path(output_dir) / output_name)
		panel_tree.write(output_path, encoding="utf-8", xml_declaration=True)
		output_paths.append(output_path)

	return output_paths


def panel_file_name(sysvar_path: str, message: MessageInfo) -> str:
	base_name = Path(sysvar_path).stem
	return f"{safe_filename(base_name)}_{safe_filename(message.namespace)}_{safe_filename(message.variable_name)}_panel.xvp"


def safe_filename(value: str) -> str:
	name = re.sub(r"[^0-9A-Za-z_]+", "_", value).strip("_")
	return name or "panel"


def parse_selected_messages(sysvar_path: str, selected_variables: Dict[str, List[str]]) -> List[MessageInfo]:
	tree = ET.parse(sysvar_path)
	root = tree.getroot()
	namespace_map: Dict[str, ET.Element] = {}

	for namespace in root.findall(".//namespace"):
		namespace_path = namespace.get("name", "")
		if namespace_path:
			namespace_map[namespace_path] = namespace

	messages: List[MessageInfo] = []
	for namespace_name, variable_names in selected_variables.items():
		namespace = namespace_map.get(namespace_name)
		if namespace is None:
			continue

		struct_map = {struct.get("name", ""): struct for struct in namespace.findall("./struct")}
		for variable_name in variable_names:
			variable = find_variable(namespace, variable_name)
			if variable is None:
				continue

			struct_name = struct_name_from_definition(variable.get("structDefinition", ""))
			struct = struct_map.get(struct_name)
			if struct is None:
				continue

			messages.append(
				MessageInfo(
					namespace=namespace_name,
					variable_name=variable_name,
					struct_name=struct_name,
					members=parse_struct_members(struct),
				)
			)

	return messages


def find_variable(namespace: ET.Element, variable_name: str) -> Optional[ET.Element]:
	for variable in namespace.findall("./variable"):
		if variable.get("name") == variable_name:
			return variable
	return None


def struct_name_from_definition(struct_definition: str) -> str:
	if "::" not in struct_definition:
		return struct_definition
	return struct_definition.rsplit("::", 1)[1]


def parse_struct_members(struct: ET.Element) -> Dict[str, StructMemberInfo]:
	members: Dict[str, StructMemberInfo] = {}
	for member in struct.findall("./structMember"):
		member_name = member.get("name", "")
		if not member_name:
			continue

		members[member_name] = StructMemberInfo(
			name=member_name,
			member_type=member.get("type", ""),
			comment=member.get("comment", ""),
			min_value=member.get("minValue", "~"),
			max_value=member.get("maxValue", "~"),
			valuetable=parse_value_table(member),
		)
	return members


def parse_value_table(member: ET.Element) -> Dict[str, str]:
	value_table = member.find("./valuetable")
	if value_table is None:
		return {}

	entries: Dict[str, str] = {}
	for entry in value_table.findall("./valuetableentry"):
		value = entry.get("value", "")
		display = entry.get("displayString", "") or entry.get("description", "")
		if value:
			entries[value] = display
	return entries


def build_panel_tree(messages: Sequence[MessageInfo]) -> ET.ElementTree:
	panel = ET.Element("Panel", {"Type": PANEL_TYPE})
	root_object = ET.SubElement(
		panel,
		"Object",
		{"Type": RUNTIME_PANEL_TYPE, "Name": "Panel", "ControlName": "xt"},
	)

	y_offset = 0
	for index, message in enumerate(messages, start=1):
		rows = collect_signal_rows(message)
		group_height = max(180, 82 + len(rows) * 50)
		add_message_group(root_object, message, rows, y_offset, group_height, index)
		y_offset += group_height + 20

	add_property(root_object, "Name", "Panel")
	add_property(root_object, "Size", f"{PANEL_WIDTH}, {max(725, y_offset)}")
	add_property(root_object, "Location", "0, 0")
	add_property(root_object, "BackColor", "255, 255, 255, 255")

	tree = ET.ElementTree(panel)
	ET.indent(tree, space="  ")
	return tree


def collect_signal_rows(message: MessageInfo) -> List[SignalRow]:
	rows: List[SignalRow] = []
	for member_name, member in message.members.items():
		if not member_name.endswith("_Rv"):
			continue

		signal_name = member_name[: -len("_Rv")]
		physical_member = message.members.get(f"{signal_name}_Pv")
		if physical_member is None:
			continue

		rows.append(
			SignalRow(
				name=signal_name,
				raw_member=member,
				physical_member=physical_member,
				use_special_member=message.members.get(f"{signal_name}_use_special_value"),
				use_inactive_member=message.members.get(f"{signal_name}_use_inactive_value"),
			)
		)
	return rows


def add_message_group(
	parent: ET.Element,
	message: MessageInfo,
	rows: Sequence[SignalRow],
	y_offset: int,
	group_height: int,
	group_index: int,
) -> None:
	group = ET.SubElement(
		parent,
		"Object",
		{"Type": GROUP_BOX_TYPE, "Name": object_name(), "ControlName": f"Group Box {group_index}"},
	)

	add_headers_and_separators(group, group_height)

	for row_index, row in enumerate(rows):
		y = 94 + row_index * 50
		add_signal_row(group, message, row, y, row_index + 1)
		add_horizontal_line(group, y + 35, row_index + 10)

	add_property(group, "Name", group.get("Name", ""))
	add_property(group, "Size", f"{GROUP_WIDTH}, {group_height}")
	add_property(group, "Location", f"0, {y_offset}")
	add_property(group, "BackColor", "WhiteSmoke")
	add_property(group, "Font", "Microsoft Sans Serif, 12.25pt")
	add_property(group, "Text", f"Message Name: {message.variable_name}")
	add_property(group, "TabIndex", str(group_index))
	add_property(group, "UseWindowsStyle", "False")


def add_headers_and_separators(group: ET.Element, group_height: int) -> None:
	add_static_text(group, "Signal Name", 50, 47, 94, 19, fore_color="255, 225, 128, 48")
	add_static_text(group, "Raw Value", 304, 47, 81, 19, fore_color="255, 225, 128, 48")
	add_static_text(group, "Physical Value", 660, 47, 120, 19, fore_color="255, 225, 128, 48")
	add_static_text(group, "Special Value", 995, 47, 120, 19, fore_color="255, 225, 128, 48")

	add_vertical_line(group, SIGNAL_RAW_SEPARATOR_X, 47, group_height - 38, 1)
	add_vertical_line(group, RAW_PHYSICAL_SEPARATOR_X, 47, group_height - 38, 2)
	add_vertical_line(group, PHYSICAL_SPECIAL_SEPARATOR_X, 47, group_height - 38, 3)
	add_horizontal_line(group, 79, 4)


def add_signal_row(group: ET.Element, message: MessageInfo, row: SignalRow, y: int, row_index: int) -> None:
	add_static_text(group, row.name, 0, y, 190, 19)
	add_value_control(
		group,
		message,
		row.raw_member,
		RAW_VALUE_CONTROL_X,
		y - 2,
		"RawValue",
		row_index * 10 + 1,
		width=RAW_TEXT_BOX_WIDTH,
	)
	add_min_max_text(group, row.raw_member, RAW_MIN_MAX_X, y - 4)
	add_value_control(group, message, row.physical_member, PHYSICAL_VALUE_CONTROL_X, y - 2, "PhysicalValue", row_index * 10 + 2)
	add_min_max_text(group, row.physical_member, PHYSICAL_MIN_MAX_X, y - 4)

	if row.use_special_member is not None:
		add_radio_button(
			group,
			message,
			row.use_special_member,
			"special value",
			SPECIAL_VALUE_X,
			y,
			row_index * 10 + 3,
		)
	if row.use_inactive_member is not None:
		add_radio_button(
			group,
			message,
			row.use_inactive_member,
			"inactive value",
			INACTIVE_VALUE_X,
			y,
			row_index * 10 + 4,
		)


def add_min_max_text(
	parent: ET.Element,
	member: StructMemberInfo,
	x: int,
	y: int,
) -> None:
	add_static_text(
		parent,
		f"min: {member.min_value}",
		x,
		y,
		120,
		16,
		font=MIN_MAX_FONT,
		fore_color="255, 0, 0, 0",
	)
	add_static_text(
		parent,
		f"max: {member.max_value}",
		x,
		y + 18,
		150,
		16,
		font=MIN_MAX_FONT,
		fore_color="255, 0, 0, 0",
	)


def add_value_control(
	parent: ET.Element,
	message: MessageInfo,
	member: StructMemberInfo,
	x: int,
	y: int,
	used_value_table: str,
	tab_index: int,
	width: int = DEFAULT_VALUE_CONTROL_WIDTH,
) -> None:
	if member.valuetable:
		add_combo_box(parent, message, member, x, y, tab_index, width=width)
	else:
		add_text_box(parent, message, member, x, y, used_value_table, tab_index, width=width)


def add_combo_box(
	parent: ET.Element,
	message: MessageInfo,
	member: StructMemberInfo,
	x: int,
	y: int,
	tab_index: int,
	width: int = DEFAULT_VALUE_CONTROL_WIDTH,
) -> None:
	control = ET.SubElement(
		parent,
		"Object",
		{"Type": COMBO_BOX_TYPE, "Name": object_name(), "ControlName": f"Combo Box {tab_index}"},
	)
	add_property(control, "Name", control.get("Name", ""))
	add_property(control, "Size", f"{width}, 23")
	add_property(control, "Location", f"{x}, {y}")
	add_property(control, "DisplayLabel", "Left")
	add_property(control, "DescriptionSize", "5, 23")
	add_property(control, "Font", "Microsoft Sans Serif, 11.25pt")
	add_property(control, "TabIndex", str(tab_index))
	add_property(control, "DescriptionText", "")
	add_property(control, "SymbolConfiguration", symbol_configuration(message, member.name))


def add_text_box(
	parent: ET.Element,
	message: MessageInfo,
	member: StructMemberInfo,
	x: int,
	y: int,
	used_value_table: str,
	tab_index: int,
	width: int = DEFAULT_VALUE_CONTROL_WIDTH,
) -> None:
	control = ET.SubElement(
		parent,
		"Object",
		{"Type": TEXT_BOX_TYPE, "Name": object_name(), "ControlName": f"Input/Output Box {tab_index}"},
	)
	add_property(control, "Name", control.get("Name", ""))
	add_property(control, "Size", f"{width}, 25")
	add_property(control, "Location", f"{x}, {y}")
	add_property(control, "AlarmGeneralSettings", alarm_general_settings(member))
	add_property(control, "AlarmLowerBkgColor", "Salmon")
	add_property(control, "AlarmLowerTextColor", "ControlText")
	add_property(control, "AlarmUpperBkgColor", "IndianRed")
	add_property(control, "AlarmUpperTextColor", "ControlText")
	add_property(control, "BoxBorderStyle", "FixedSingle")
	add_property(control, "DisplayLabel", "Left")
	add_property(control, "BoxFont", "Verdana, 11.25pt")
	add_property(control, "AlarmLowerFont", "Verdana, 11.25pt")
	add_property(control, "AlarmUpperFont", "Verdana, 11.25pt")
	add_property(control, "TextFont", "Verdana, 7pt, style=Bold")
	add_property(control, "TabIndex", str(tab_index))
	add_property(control, "DescriptionText", "")
	add_property(control, "ValueDecimalPlaces", "0" if member.member_type == "int" else "3")
	add_property(control, "ValueDisplay", value_display(member))
	add_property(control, "UsedValueTable", used_value_table)
	add_property(control, "DescriptionSize", "5, 25")
	add_property(control, "SymbolConfiguration", symbol_configuration(message, member.name))


def add_radio_button(
	parent: ET.Element,
	message: MessageInfo,
	member: StructMemberInfo,
	text: str,
	x: int,
	y: int,
	tab_index: int,
) -> None:
	control = ET.SubElement(
		parent,
		"Object",
		{"Type": RADIO_BUTTON_TYPE, "Name": object_name(), "ControlName": f"Radio Button {tab_index}"},
	)
	add_property(control, "Name", control.get("Name", ""))
	add_property(control, "Size", "96, 17")
	add_property(control, "Location", f"{x}, {y}")
	add_property(control, "Text", text)
	add_property(control, "TabIndex", str(tab_index))
	add_property(control, "SymbolConfiguration", symbol_configuration(message, member.name))


def alarm_general_settings(member: StructMemberInfo) -> str:
	lower_limit = member.min_value if member.min_value != "~" else DEFAULT_LOWER_LIMIT
	upper_limit = member.max_value if member.max_value != "~" else DEFAULT_UPPER_LIMIT
	return f"1;3;{lower_limit};{upper_limit}"


def value_display(member: StructMemberInfo) -> str:
	if member.member_type == "int":
		return "Decimal"
	return "Double"


def add_static_text(
	parent: ET.Element,
	text: str,
	x: int,
	y: int,
	width: int,
	height: int,
	fore_color: Optional[str] = None,
	font: str = "Microsoft Sans Serif, 11.25pt",
) -> None:
	control = ET.SubElement(
		parent,
		"Object",
		{"Type": STATIC_TEXT_TYPE, "Name": object_name(), "ControlName": f"Static Text {short_id()}"},
	)
	add_property(control, "Name", control.get("Name", ""))
	add_property(control, "Size", f"{width}, {height}")
	add_property(control, "Location", f"{x}, {y}")
	if fore_color:
		add_property(control, "ForeColor", fore_color)
	add_property(control, "Font", font)
	add_property(control, "Text", text)


def add_vertical_line(parent: ET.Element, x: int, y: int, height: int, tab_index: int) -> None:
	add_canvas(parent, x, y, 2, height, tab_index)


def add_horizontal_line(parent: ET.Element, y: int, tab_index: int) -> None:
	add_canvas(parent, -5, y, GROUP_WIDTH, 3, tab_index)


def add_canvas(parent: ET.Element, x: int, y: int, width: int, height: int, tab_index: int) -> None:
	control = ET.SubElement(
		parent,
		"Object",
		{"Type": CANVAS_TYPE, "Name": object_name(), "ControlName": f"Canvas {tab_index}"},
	)
	add_property(control, "Name", control.get("Name", ""))
	add_property(control, "Size", f"{width}, {height}")
	add_property(control, "Location", f"{x}, {y}")
	add_property(control, "BackColor", "255, 31, 73, 125")
	add_property(control, "TabIndex", str(tab_index))


def symbol_configuration(message: MessageInfo, member_name: str) -> str:
	return f"8;128;{message.namespace};;{message.variable_name};{member_name};2;;;-1;;;Value;;;0"


def add_property(parent: ET.Element, name: str, value: str) -> None:
	prop = ET.SubElement(parent, "Property", {"Name": name})
	prop.text = value


def object_name() -> str:
	return f"X{uuid.uuid4().hex}"


def short_id() -> str:
	return uuid.uuid4().hex[:8]
