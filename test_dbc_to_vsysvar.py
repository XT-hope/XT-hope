from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

from xodr_converter.dbc_to_vsysvar import (
	build_vsysvar_tree,
	convert_dbc_files_to_vsysvar,
	parse_dbc_text,
	parse_dbc_spec,
	decode_dbc_bytes,
	read_text_file,
)


CONTROL_DBC = """
VERSION ""

NS_ :
	CM_
	BA_
	BA_DEF_

BS_:

BU_: Media ADC EPS

BO_ 573 Media_0x23D: 8 Media
 SG_ PAD_AVPPauseReq_S : 0|1@1+ (1,0) [0|1] ""  ADC
 SG_ EPS_SteerPinionAg : 44|16@1- (0.1,0) [-720|720] "deg"  ADC

BA_DEF_ SG_ "GenSigStartValue" FLOAT 0 100000000000;
CM_ SG_ 573 PAD_AVPPauseReq_S "用户暂停";
CM_ SG_ 573 EPS_SteerPinionAg "转向小齿轮角度";
BA_ "GenSigStartValue" SG_ 573 PAD_AVPPauseReq_S 0;
BA_ "GenSigStartValue" SG_ 573 EPS_SteerPinionAg 2810;
"""


CHASSIS_DBC = """
VERSION ""

NS_ :
	BA_
	BA_DEF_

BS_:

BU_: ABS ADC

BO_ 100 VehicleStatus: 8 ABS
 SG_ VehicleSpeed : 0|16@1+ (0.01,0) [0|250] "km/h"  ADC

BA_DEF_ SG_ "GenSigStartValue" FLOAT 0 100000000000;
BA_ "GenSigStartValue" SG_ 100 VehicleSpeed 1234;
"""


INTEGER_PHYSICAL_DBC = """
VERSION ""

NS_ :

BS_:

BU_: BCM ADC

BO_ 200 BodyStatus: 8 BCM
 SG_ DoorStep : 0|8@1+ (2,0) [0|510] "" ADC
"""


FRACTIONAL_BOUND_DBC = """
VERSION ""

NS_ :

BS_:

BU_: ACC ADC

BO_ 201 ACC_0x0C9: 8 ACC
 SG_ Set_Speed_S : 0|9@1+ (1,0) [0E-008|255.50000000] "" ADC
"""


INVALID_RAW_RANGE_DBC = """
VERSION ""

NS_ :

BS_:

BU_: VCU VCP

BO_ 300 VCU_0x12C: 8 VCU
 SG_ VCU_AX : 16|12@1+ (0.0096153846153846193878234061003240640275180339813232421875,-19.69230769230770050626233569346368312835693359375) [-19.69230769|-19.69230769] "" VCP
"""


ENUM_DBC = """
VERSION ""

NS_ :
	VAL_
	BA_
	BA_DEF_
	BA_DEF_DEF_

BS_:

BU_: LDA ADC

BA_DEF_ BO_ "GenMsgSendType" ENUM "Cycle", "Event", "IfActive", "CE" ,"CA", "NoMsgSendType";
BA_DEF_DEF_ "GenMsgSendType" "Cycle";
BA_DEF_ BO_ "GenMsgCycleTime" INT 0 65535;
BA_DEF_DEF_ "GenMsgCycleTime" 10;
BA_DEF_ BO_ "GenMsgCycleTimeFast" INT 0 65535;
BA_DEF_DEF_ "GenMsgCycleTimeFast" 0;
BA_DEF_ BO_ "GenMsgNrOfRepetition" INT 0 255;
BA_DEF_DEF_ "GenMsgNrOfRepetition" 0;

BO_ 567 LDA_0x237: 8 LDA
 SG_ LDA_Func_Dis_Confm_Button : 0|2@1+ (1,0) [0|3] "" ADC

VAL_ 567 LDA_Func_Dis_Confm_Button 0 "Invalid" 1 "Europe" 2 "Other" 3 "Reserved";
BA_ "GenMsgSendType" BO_ 567 3;
BA_ "GenMsgCycleTime" BO_ 567 20;
BA_ "GenMsgCycleTimeFast" BO_ 567 5;
BA_ "GenMsgNrOfRepetition" BO_ 567 3;
"""


WIDE_RAW_DBC = """
VERSION ""

NS_ :

BS_:

BU_: MAC ADC

BO_ 459 MAC_0x1CB: 8 MAC
 SG_ CutOutMAC_1CB_S : 0|48@1+ (1,0) [0|281474976710655] "" ADC
"""


class DbcToVsysvarTests(unittest.TestCase):
	def test_builds_struct_members_and_message_variable(self) -> None:
		database = parse_dbc_text(CONTROL_DBC)
		tree = build_vsysvar_tree([("ControlCAN", database)])
		root = tree.getroot()

		namespace = root.find("./namespace/namespace[@name='ControlCAN']")
		self.assertIsNotNone(namespace)

		struct = namespace.find("./struct[@name='media_0x23d']")
		self.assertIsNotNone(struct)
		self.assertEqual("False", struct.attrib["isUnion"])
		self.assertEqual("False", struct.attrib["definedBinaryLayout"])

		members = {member.attrib["name"]: member.attrib for member in struct.findall("structMember")}
		self.assertEqual(9, len(members))

		node_member = members["Media_0x23D_node"]
		self.assertEqual("string", node_member["type"])
		self.assertEqual("0", node_member["bitcount"])
		self.assertEqual("false", node_member["isSigned"])
		self.assertEqual("65001", node_member["encoding"])
		self.assertEqual("Media", node_member["startValue"])

		pause_pv = members["PAD_AVPPauseReq_S_Pv"]
		self.assertEqual("int", pause_pv["type"])
		self.assertEqual("false", pause_pv["isSigned"])
		self.assertEqual("0", pause_pv["startValue"])
		self.assertEqual("0", pause_pv["minValue"])
		self.assertEqual("1", pause_pv["maxValue"])
		self.assertEqual("用户暂停", pause_pv["comment"])

		angle_pv = members["EPS_SteerPinionAg_Pv"]
		self.assertEqual("double", angle_pv["type"])
		self.assertEqual("true", angle_pv["isSigned"])
		self.assertEqual("281", angle_pv["startValue"])
		self.assertEqual("-720", angle_pv["minValue"])
		self.assertEqual("720", angle_pv["maxValue"])

		angle_rv = members["EPS_SteerPinionAg_Rv"]
		self.assertEqual("int", angle_rv["type"])
		self.assertEqual("2810", angle_rv["startValue"])
		self.assertEqual("-7200", angle_rv["minValue"])
		self.assertEqual("7200", angle_rv["maxValue"])

		angle_factor = members["EPS_SteerPinionAg_Factor"]
		self.assertEqual("double", angle_factor["type"])
		self.assertEqual("0.1", angle_factor["startValue"])
		self.assertNotIn("minValue", angle_factor)
		self.assertNotIn("maxValue", angle_factor)

		variable = namespace.find("./variable[@name='Media_0x23D']")
		self.assertIsNotNone(variable)
		self.assertEqual("struct", variable.attrib["type"])
		self.assertEqual("ControlCAN::media_0x23d", variable.attrib["structDefinition"])
		self.assertEqual("512", variable.attrib["bitcount"])

	def test_writes_node_info_struct_from_bu_nodes(self) -> None:
		database = parse_dbc_text(CONTROL_DBC)
		tree = build_vsysvar_tree([("ControlCAN", database)])
		root = tree.getroot()
		node_struct = root.find("./namespace/namespace[@name='ControlCAN']/struct[@name='controlcan_node_info']")
		node_variable = root.find("./namespace/namespace[@name='ControlCAN']/variable[@name='ControlCAN_Node_Info']")

		self.assertIsNotNone(node_struct)
		self.assertIsNotNone(node_variable)
		self.assertEqual("96", node_variable.attrib["bitcount"])
		self.assertEqual("ControlCAN::controlcan_node_info", node_variable.attrib["structDefinition"])
		members = {member.attrib["name"]: member.attrib for member in node_struct.findall("structMember")}
		self.assertEqual({"Media_MsgOn", "ADC_MsgOn", "EPS_MsgOn"}, set(members))
		for attrs in members.values():
			self.assertEqual("int", attrs["type"])
			self.assertEqual("32", attrs["bitcount"])
			self.assertEqual("1", attrs["startValue"])
			self.assertEqual("0", attrs["minValue"])
			self.assertEqual("1", attrs["maxValue"])

	def test_writes_multiple_dbc_namespaces_to_one_file(self) -> None:
		with tempfile.TemporaryDirectory() as temp_dir:
			temp_path = Path(temp_dir)
			control_path = temp_path / "control.dbc"
			chassis_path = temp_path / "chassis.dbc"
			output_path = temp_path / "vehicle.vsysvar"
			control_path.write_text(CONTROL_DBC, encoding="utf-8")
			chassis_path.write_text(CHASSIS_DBC, encoding="utf-8")

			convert_dbc_files_to_vsysvar(
				[
					("ControlCAN", str(control_path)),
					("ChassisCAN", str(chassis_path)),
				],
				str(output_path),
			)

			root = ET.parse(output_path).getroot()
			self.assertEqual("4", root.attrib["version"])
			self.assertIsNotNone(root.find("./namespace/namespace[@name='ControlCAN']"))
			self.assertIsNotNone(root.find("./namespace/namespace[@name='ChassisCAN']"))
			self.assertIsNotNone(
				root.find("./namespace/namespace[@name='ChassisCAN']/variable[@name='VehicleStatus']")
			)

	def test_uses_int_for_integral_physical_values_in_int_range(self) -> None:
		database = parse_dbc_text(INTEGER_PHYSICAL_DBC)
		tree = build_vsysvar_tree([("BodyCAN", database)])
		root = tree.getroot()
		member = root.find(
			"./namespace/namespace[@name='BodyCAN']/struct[@name='bodystatus']"
			"/structMember[@name='DoorStep_Pv']"
		)

		self.assertIsNotNone(member)
		self.assertEqual("int", member.attrib["type"])
		self.assertEqual("0", member.attrib["minValue"])
		self.assertEqual("510", member.attrib["maxValue"])

	def test_uses_double_when_physical_bounds_are_fractional(self) -> None:
		database = parse_dbc_text(FRACTIONAL_BOUND_DBC)
		tree = build_vsysvar_tree([("ControlCAN", database)])
		root = tree.getroot()
		member = root.find(
			"./namespace/namespace[@name='ControlCAN']/struct[@name='acc_0x0c9']"
			"/structMember[@name='Set_Speed_S_Pv']"
		)

		self.assertIsNotNone(member)
		self.assertEqual("double", member.attrib["type"])
		self.assertEqual("0", member.attrib["minValue"])
		self.assertEqual("255.5", member.attrib["maxValue"])

	def test_omits_rv_bounds_when_physical_range_cannot_map_to_raw_integer(self) -> None:
		database = parse_dbc_text(INVALID_RAW_RANGE_DBC)
		tree = build_vsysvar_tree([("ControlCAN", database)])
		root = tree.getroot()
		member = root.find(
			"./namespace/namespace[@name='ControlCAN']/struct[@name='vcu_0x12c']"
			"/structMember[@name='VCU_AX_Rv']"
		)

		self.assertIsNotNone(member)
		self.assertEqual("int", member.attrib["type"])
		self.assertEqual("0", member.attrib["startValue"])
		self.assertNotIn("minValue", member.attrib)
		self.assertNotIn("maxValue", member.attrib)

	def test_reads_gb18030_encoded_chinese_comments(self) -> None:
		with tempfile.TemporaryDirectory() as temp_dir:
			dbc_path = Path(temp_dir) / "control_gbk.dbc"
			dbc_path.write_bytes(CONTROL_DBC.encode("gb18030"))

			text = read_text_file(str(dbc_path), encoding="gb18030")
			database = parse_dbc_text(text)
			tree = build_vsysvar_tree([("ControlCAN", database)])
			root = tree.getroot()
			member = root.find(
				"./namespace/namespace[@name='ControlCAN']/struct[@name='media_0x23d']"
				"/structMember[@name='PAD_AVPPauseReq_S_Pv']"
			)

			self.assertIsNotNone(member)
			self.assertEqual("用户暂停", member.attrib["comment"])

	def test_requested_encoding_is_used_directly(self) -> None:
		with tempfile.TemporaryDirectory() as temp_dir:
			dbc_path = Path(temp_dir) / "control_gbk.dbc"
			dbc_path.write_bytes(CONTROL_DBC.encode("gb18030"))

			text = read_text_file(str(dbc_path), encoding="gb18030")

			self.assertIn('CM_ SG_ 573 PAD_AVPPauseReq_S "用户暂停";', text)

	def test_decode_uses_utf8_sig_by_default(self) -> None:
		text = decode_dbc_bytes(CONTROL_DBC.encode("utf-8-sig"))

		self.assertIn('CM_ SG_ 573 PAD_AVPPauseReq_S "用户暂停";', text)

	def test_writes_signal_value_table_from_val_definitions(self) -> None:
		database = parse_dbc_text(ENUM_DBC)
		tree = build_vsysvar_tree([("ControlCAN", database)])
		root = tree.getroot()
		pv_member = root.find(
			"./namespace/namespace[@name='ControlCAN']/struct[@name='lda_0x237']"
			"/structMember[@name='LDA_Func_Dis_Confm_Button_Pv']"
		)
		member = root.find(
			"./namespace/namespace[@name='ControlCAN']/struct[@name='lda_0x237']"
			"/structMember[@name='LDA_Func_Dis_Confm_Button_Rv']"
		)

		self.assertIsNotNone(pv_member)
		self.assertEqual("int", pv_member.attrib["type"])
		self.assertIsNotNone(member)
		self.assertEqual("int", member.attrib["type"])
		value_table = member.find("./valuetable[@name='LDA_Func_Dis_Confm_ButtonVt']")
		self.assertIsNotNone(value_table)
		entries = {entry.attrib["value"]: entry.attrib["displayString"] for entry in value_table.findall("valuetableentry")}
		self.assertEqual(
			{
				"0": "Invalid",
				"1": "Europe",
				"2": "Other",
				"3": "Reserved",
			},
			entries,
		)

	def test_writes_message_info_struct_from_message_attributes(self) -> None:
		database = parse_dbc_text(ENUM_DBC)
		tree = build_vsysvar_tree([("ControlCAN", database)])
		root = tree.getroot()
		info_struct = root.find("./namespace/namespace[@name='ControlCAN']/struct[@name='lda_0x237_info']")
		info_variable = root.find("./namespace/namespace[@name='ControlCAN']/variable[@name='LDA_0x237_Info']")

		self.assertIsNotNone(info_struct)
		self.assertIsNotNone(info_variable)
		self.assertEqual("192", info_variable.attrib["bitcount"])

		members = {member.attrib["name"]: member for member in info_struct.findall("structMember")}
		self.assertEqual("1", members["LDA_0x237_MsgOn"].attrib["startValue"])
		self.assertEqual("0", members["LDA_0x237_MsgOff"].attrib["startValue"])
		self.assertEqual("3", members["LDA_0x237_MsgSendType"].attrib["startValue"])
		self.assertEqual("20", members["LDA_0x237_MsgCycleTime"].attrib["startValue"])
		self.assertEqual("5", members["LDA_0x237_MsgCycleTimeFast"].attrib["startValue"])
		self.assertEqual("3", members["LDA_0x237_MsgNrOfRepetition"].attrib["startValue"])
		for member in members.values():
			self.assertEqual("32", member.attrib["bitcount"])
			self.assertEqual("int", member.attrib["type"])

		value_table = members["LDA_0x237_MsgSendType"].find("./valuetable[@name='LDA_0x237_MsgSendTypeVt']")
		self.assertIsNotNone(value_table)
		send_type_entries = {
			entry.attrib["value"]: entry.attrib["displayString"]
			for entry in value_table.findall("valuetableentry")
		}
		self.assertEqual("Cycle", send_type_entries["0"])
		self.assertEqual("CE", send_type_entries["3"])
		self.assertEqual("CA", send_type_entries["4"])

	def test_omits_int_bounds_that_exceed_canoe_int_range(self) -> None:
		database = parse_dbc_text(WIDE_RAW_DBC)
		tree = build_vsysvar_tree([("ControlCAN", database)])
		root = tree.getroot()
		pv_member = root.find(
			"./namespace/namespace[@name='ControlCAN']/struct[@name='mac_0x1cb']"
			"/structMember[@name='CutOutMAC_1CB_S_Pv']"
		)
		member = root.find(
			"./namespace/namespace[@name='ControlCAN']/struct[@name='mac_0x1cb']"
			"/structMember[@name='CutOutMAC_1CB_S_Rv']"
		)

		self.assertIsNotNone(pv_member)
		self.assertEqual("double", pv_member.attrib["type"])
		self.assertIsNotNone(member)
		self.assertEqual("int", member.attrib["type"])
		self.assertEqual("0", member.attrib["minValue"])
		self.assertNotIn("maxValue", member.attrib)

	def test_parses_cli_dbc_specs(self) -> None:
		self.assertEqual(("ControlCAN", "control.dbc"), parse_dbc_spec("ControlCAN=control.dbc"))
		namespace, path = parse_dbc_spec("/tmp/body-network.dbc")
		self.assertEqual("body_network", namespace)
		self.assertEqual("/tmp/body-network.dbc", path)


if __name__ == "__main__":
	unittest.main()
