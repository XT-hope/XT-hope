"""capl_generator 的离线测试：用构造的 .vsysvar + config + project.json 验证生成结果。"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from capl_generator import generate_capl, parse_vsysvar, load_channel_mapping


VSYSVAR = """<?xml version='1.0' encoding='utf-8'?>
<systemvariables version="4">
  <namespace name="" comment="" interface="">
    <namespace name="control" comment="" interface="">
      <variable anlyzLocal="2" readOnly="false" valueSequence="false" unit="" name="control_Node_On" comment="" bitcount="32" isSigned="false" encoding="65001" type="int" startValue="1" minValue="0" maxValue="1" />
      <struct name="control_node_info" isUnion="False" definedBinaryLayout="False" comment="">
        <structMember relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" name="IPB_MsgOn" comment="" bitcount="32" isSigned="false" encoding="65001" type="int" startValue="1" minValue="0" maxValue="1" />
        <structMember relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" name="EPS_MsgOn" comment="" bitcount="32" isSigned="false" encoding="65001" type="int" startValue="1" minValue="0" maxValue="1" />
      </struct>
      <variable anlyzLocal="2" readOnly="false" valueSequence="false" unit="" name="control_Node_Info" comment="" bitcount="64" isSigned="true" encoding="65001" type="struct" structDefinition="control::control_node_info" />
      <struct name="ipb_0x10c_info" isUnion="False" definedBinaryLayout="False" comment="">
        <structMember relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" name="IPB_0x10C_MsgOn" comment="" bitcount="32" isSigned="false" encoding="65001" type="int" startValue="1" minValue="0" maxValue="1" />
        <structMember relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" name="IPB_0x10C_MsgOff" comment="" bitcount="32" isSigned="false" encoding="65001" type="int" startValue="0" minValue="0" maxValue="1" />
        <structMember relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" name="IPB_0x10C_MsgSendType" comment="" bitcount="32" isSigned="false" encoding="65001" type="int" startValue="0" minValue="0" maxValue="5" />
        <structMember relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" name="IPB_0x10C_MsgCycleTime" comment="" bitcount="32" isSigned="false" encoding="65001" type="int" startValue="10" minValue="0" maxValue="65535" />
      </struct>
      <variable anlyzLocal="2" readOnly="false" valueSequence="false" unit="" name="IPB_0x10C_Info" comment="" bitcount="128" isSigned="true" encoding="65001" type="struct" structDefinition="control::ipb_0x10c_info" />
      <struct name="ipb_0x10c" isUnion="False" definedBinaryLayout="False" comment="">
        <structMember relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" name="IPB_0x10C_node" comment="" bitcount="0" isSigned="false" encoding="65001" type="string" startValue="IPB" />
        <structMember relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" name="Checksum_10C_S_Pv" comment="" bitcount="32" isSigned="false" encoding="65001" type="int" startValue="0" minValue="0" maxValue="65535" />
        <structMember relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" name="Checksum_10C_S_Rv" comment="" bitcount="32" isSigned="false" encoding="65001" type="int" startValue="0" minValue="0" maxValue="65535" />
        <structMember relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" name="Checksum_10C_S_Factor" comment="" bitcount="64" isSigned="false" encoding="65001" type="float" startValue="1" />
        <structMember relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" name="Checksum_10C_S_Offset" comment="" bitcount="64" isSigned="false" encoding="65001" type="float" startValue="0" />
        <structMember relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" name="Counter_10C_S_Pv" comment="" bitcount="32" isSigned="false" encoding="65001" type="int" startValue="0" minValue="0" maxValue="15" />
        <structMember relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" name="Counter_10C_S_Rv" comment="" bitcount="32" isSigned="false" encoding="65001" type="int" startValue="0" minValue="0" maxValue="15" />
        <structMember relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" name="Counter_10C_S_Factor" comment="" bitcount="64" isSigned="false" encoding="65001" type="float" startValue="1" />
        <structMember relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" name="Counter_10C_S_Offset" comment="" bitcount="64" isSigned="false" encoding="65001" type="float" startValue="0" />
        <structMember relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" name="Vehicle_speed_Pv" comment="" bitcount="64" isSigned="false" encoding="65001" type="float" startValue="0" minValue="0" maxValue="281.4625" />
        <structMember relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" name="Vehicle_speed_Rv" comment="" bitcount="32" isSigned="false" encoding="65001" type="int" startValue="0" minValue="0" maxValue="4094" />
        <structMember relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" name="Vehicle_speed_Factor" comment="" bitcount="64" isSigned="false" encoding="65001" type="float" startValue="0.06875" />
        <structMember relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" name="Vehicle_speed_Offset" comment="" bitcount="64" isSigned="false" encoding="65001" type="float" startValue="0" />
        <structMember relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" name="Vehicle_speed_has_special_value" comment="" bitcount="32" isSigned="false" encoding="65001" type="int" startValue="0" minValue="0" maxValue="1" />
        <structMember relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" name="Vehicle_speed_use_special_value" comment="" bitcount="32" isSigned="false" encoding="65001" type="int" startValue="0" minValue="0" maxValue="1" />
        <structMember relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" name="Vehicle_speed_has_inactive_value" comment="" bitcount="32" isSigned="false" encoding="65001" type="int" startValue="1" minValue="0" maxValue="1" />
        <structMember relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" name="Vehicle_speed_use_inactive_value" comment="" bitcount="32" isSigned="false" encoding="65001" type="int" startValue="0" minValue="0" maxValue="1" />
        <structMember relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" name="Vehicle_speed_inactive_value" comment="" bitcount="32" isSigned="false" encoding="65001" type="int" startValue="4095" />
      </struct>
      <variable anlyzLocal="2" readOnly="false" valueSequence="false" unit="" name="IPB_0x10C" comment="" bitcount="512" isSigned="true" encoding="65001" type="struct" structDefinition="control::ipb_0x10c" />
      <struct name="ipb_0x200" isUnion="False" definedBinaryLayout="False" comment="">
        <structMember relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" name="IPB_0x200_node" comment="" bitcount="0" isSigned="false" encoding="65001" type="string" startValue="IPB" />
        <structMember relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" name="Wheel_speed_Pv" comment="" bitcount="64" isSigned="false" encoding="65001" type="float" startValue="0" minValue="0" maxValue="100" />
        <structMember relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" name="Wheel_speed_Rv" comment="" bitcount="32" isSigned="false" encoding="65001" type="int" startValue="0" minValue="0" maxValue="200" />
        <structMember relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" name="Wheel_speed_Factor" comment="" bitcount="64" isSigned="false" encoding="65001" type="float" startValue="0.5" />
        <structMember relativeOffset="0" byteOrder="0" isOptional="False" isHidden="False" name="Wheel_speed_Offset" comment="" bitcount="64" isSigned="false" encoding="65001" type="float" startValue="0" />
      </struct>
      <variable anlyzLocal="2" readOnly="false" valueSequence="false" unit="" name="IPB_0x200" comment="" bitcount="256" isSigned="true" encoding="65001" type="struct" structDefinition="control::ipb_0x200" />
    </namespace>
  </namespace>
</systemvariables>
"""


def main():
    base = Path("/tmp/test_capl/proj")
    (base / "CANoe" / "dbc_file").mkdir(parents=True, exist_ok=True)

    sysvar_path = base / "CANoe" / "system_variable" / "demo.vsysvar"
    sysvar_path.parent.mkdir(parents=True, exist_ok=True)
    sysvar_path.write_text(VSYSVAR, encoding="utf-8")

    project_json = {
        "canoe": {
            "dbc_files": {
                "CANoe/dbc_file/VCP_Control.dbc": {
                    "path": "CANoe/dbc_file/VCP_Control.dbc",
                    "short_name": "Control",
                    "channel": 0,
                }
            }
        }
    }
    (base / "project.json").write_text(json.dumps(project_json, ensure_ascii=False, indent=2), encoding="utf-8")

    config = {
        "dbc_configs": [
            {
                "dbc_path": "D:\\Test\\proj\\CANoe\\dbc_file\\VCP_Control.dbc",
                "dbc_name": "control",
                "center_node": "VCP",
                "senders": [
                    {
                        "sender_node": "IPB",
                        "messages": [
                            {
                                "message_name": "IPB_0x10C",
                                "has_validation": True,
                                "check_signal": "Checksum_10C_S",
                                "counter_signal": "Counter_10C_S",
                                "check_method": "crc16",
                                "check_parameters": {
                                    "poly": "0x1021",
                                    "init": "0xFFFF",
                                    "refIn": "false",
                                    "refOut": "false",
                                    "xorOut": "0x0000",
                                },
                            },
                            {
                                "message_name": "IPB_0x200",
                                "has_validation": False,
                            },
                        ],
                    }
                ],
            }
        ],
        "selected_system_variable_file": str(sysvar_path),
    }

    print("=== parse_vsysvar ===")
    parsed = parse_vsysvar(str(sysvar_path))
    msgs = parsed.messages
    for name, model in msgs.items():
        print(f"message {name}: signals = {[s.name for s in model.signals]}")
        for s in model.signals:
            print(f"  {s.name}: factor={s.factor} offset={s.offset} rv=[{s.rv_min},{s.rv_max}]"
                  f" special={s.has_special_value} inactive={s.has_inactive_value}")

    print("\n=== load_channel_mapping ===")
    print(load_channel_mapping(base))

    print("\n=== generate_capl ===")
    files = generate_capl(config, base)
    for f in files:
        print("generated:", f)
        print("-" * 60)
        print(Path(f).read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
