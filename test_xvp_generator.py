from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

from xodr_converter.xvp_generator import generation_xvp


SYSVAR_XML = """<?xml version="1.0" encoding="utf-8"?>
<systemvariables version="4">
  <namespace name="" comment="" interface="">
    <namespace name="control" comment="" interface="">
      <struct name="ipb_0x10c" isUnion="False" definedBinaryLayout="False" comment="">
        <structMember relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" name="VehicleSpeed_Rv" comment="" bitcount="64" isSigned="false" encoding="65001" type="int" startValue="0" minValue="0" maxValue="3">
          <valuetable name="VehicleSpeedVt" definesMinMax="false">
            <valuetableentry value="0" lowerBound="0" upperBound="0" description="Invalid" displayString="Invalid" />
            <valuetableentry value="1" lowerBound="1" upperBound="1" description="Close" displayString="Close" />
          </valuetable>
        </structMember>
        <structMember relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" name="VehicleSpeed_Pv" comment="" bitcount="64" isSigned="false" encoding="65001" type="double" startValue="0" minValue="0" maxValue="102.2" />
        <structMember relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" name="VehicleSpeed_use_special_value" comment="" bitcount="64" isSigned="false" encoding="65001" type="int" startValue="0" minValue="0" maxValue="1" />
        <structMember relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" name="VehicleSpeed_use_inactive_value" comment="" bitcount="64" isSigned="false" encoding="65001" type="int" startValue="0" minValue="0" maxValue="1" />
        <structMember relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" name="NoRange_Rv" comment="" bitcount="64" isSigned="false" encoding="65001" type="int" startValue="0" />
        <structMember relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" name="NoRange_Pv" comment="" bitcount="64" isSigned="false" encoding="65001" type="double" startValue="0" />
      </struct>
      <struct name="eps_0x06d" isUnion="False" definedBinaryLayout="False" comment="">
        <structMember relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" name="SteerAngle_Rv" comment="" bitcount="64" isSigned="true" encoding="65001" type="int" startValue="0" minValue="-7200" maxValue="7200" />
        <structMember relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" name="SteerAngle_Pv" comment="" bitcount="64" isSigned="true" encoding="65001" type="double" startValue="0" minValue="-720" maxValue="720" />
        <structMember relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" name="SteerAngle_use_special_value" comment="" bitcount="64" isSigned="false" encoding="65001" type="int" startValue="0" minValue="0" maxValue="1" />
        <structMember relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" name="SteerAngle_use_inactive_value" comment="" bitcount="64" isSigned="false" encoding="65001" type="int" startValue="0" minValue="0" maxValue="1" />
      </struct>
      <variable anlyzLocal="2" readOnly="false" valueSequence="false" unit="" name="IPB_0x10C" comment="" bitcount="256" isSigned="true" encoding="65001" type="struct" structDefinition="control::ipb_0x10c" />
      <variable anlyzLocal="2" readOnly="false" valueSequence="false" unit="" name="EPS_0x06D" comment="" bitcount="256" isSigned="true" encoding="65001" type="struct" structDefinition="control::eps_0x06d" />
      <variable anlyzLocal="2" readOnly="false" valueSequence="false" unit="" name="IPB_0x10C_Info" comment="" bitcount="128" isSigned="true" encoding="65001" type="struct" structDefinition="control::ipb_0x10c_info" />
    </namespace>
  </namespace>
</systemvariables>
"""


class XvpGeneratorTests(unittest.TestCase):
	def test_generates_xvp_for_selected_message_variables(self) -> None:
		with tempfile.TemporaryDirectory() as temp_dir:
			sysvar_path = Path(temp_dir) / "demo.vsysvar"
			sysvar_path.write_text(SYSVAR_XML, encoding="utf-8")

			output_paths = generation_xvp(
				str(sysvar_path),
				{"control": ["IPB_0x10C", "EPS_0x06D"]},
				temp_dir,
			)

			self.assertEqual(2, len(output_paths))
			self.assertTrue(any(path.endswith("demo_control_IPB_0x10C_panel.xvp") for path in output_paths))
			self.assertTrue(any(path.endswith("demo_control_EPS_0x06D_panel.xvp") for path in output_paths))
			output_path = next(path for path in output_paths if path.endswith("demo_control_IPB_0x10C_panel.xvp"))
			self.assertTrue(Path(output_path).exists())
			root = ET.parse(output_path).getroot()
			self.assertEqual("Panel", root.tag)

			group_texts = [
				prop.text
				for prop in root.findall(".//Object/Property[@Name='Text']")
				if prop.text
			]
			self.assertIn("Message Name: IPB_0x10C", group_texts)
			self.assertIn("VehicleSpeed", group_texts)
			self.assertIn("min: 0", group_texts)
			self.assertIn("max: 102.2", group_texts)
			self.assertIn("min: ~", group_texts)
			self.assertIn("max: ~", group_texts)
			min_text = next(
				obj
				for obj in root.findall(".//Object")
				if any(prop.get("Name") == "Text" and prop.text == "min: 0" for prop in obj.findall("./Property"))
			)
			min_font = min_text.find("./Property[@Name='Font']")
			self.assertIsNotNone(min_font)
			self.assertEqual("Microsoft Sans Serif, 9.25pt", min_font.text)

			object_types = [obj.get("Type", "") for obj in root.findall(".//Object")]
			self.assertTrue(any("ComboBoxControl" in obj_type for obj_type in object_types))
			self.assertTrue(any("TextBoxControl" in obj_type for obj_type in object_types))
			self.assertTrue(any("RadioButtonControl" in obj_type for obj_type in object_types))

			symbol_configurations = [
				prop.text
				for prop in root.findall(".//Property[@Name='SymbolConfiguration']")
				if prop.text
			]
			self.assertIn(
				"8;128;control;;IPB_0x10C;VehicleSpeed_Rv;2;;;-1;;;Value;;;0",
				symbol_configurations,
			)
			self.assertIn(
				"8;128;control;;IPB_0x10C;VehicleSpeed_Pv;2;;;-1;;;Value;;;0",
				symbol_configurations,
			)


if __name__ == "__main__":
	unittest.main()
