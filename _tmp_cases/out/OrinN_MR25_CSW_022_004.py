# -*- coding: utf-8 -*-
# 本文件由 dsl_to_py_case.py 自动生成，请勿手工编辑。
# META: test_point=弯中R50_超出安全过弯车速38km/h priority=P0-高 owner=auto scenario_id=48 scenario_name=Csw_Straight200_50RadiusCurve_YellowSolidLine_40kph_InCurve.mat

__name__ = 'OrinN_MR25_CSW_022_004'
URLmapping = ['VDC_Fault', 'CSW_Stats_S']

URLTests = [{'description': '初始化场景', 'steps': [{'action': 'SetScenario', 'scenario_id': 48}]}, {'description': 'S1', 'steps': [{'action': 'SetSysVar', 'namespace': 'FunctionSwitch', 'var_name': 'CSW_Enable_S', 'value': 1}, {'action': 'SetSignal', 'signal': 'VDC_Fault', 'value': 1}, {'action': 'Wait', 'wait_time': 0.2}, {'action': 'CheckSignal', 'signal': 'CSW_Stats_S', 'value': 3, 'timeout': 1.5, 'wait_time': 0.2}, {'action': 'CheckSignal', 'signal': 'CSW_Stats_S', 'value': [2, 3], 'timeout': 1.0}]}, {'description': 'S2', 'steps': [{'action': 'SetSysVar', 'namespace': 'simulink', 'var_name': 'dynamic_disconnect', 'value': 1}, {'action': 'SetSysVar', 'namespace': 'FunctionSwitch', 'var_name': 'CSW_Enable_S', 'value': 1}, {'action': 'CheckSignal', 'signal': 'CSW_Stats_S', 'value': 3, 'timeout': 1.5, 'wait_time': 0.2}]}, {'description': 'S3', 'steps': [{'action': 'SetSysVar', 'namespace': 'FunctionSwitch', 'var_name': 'CSW_Enable_S', 'value': 1}]}, {'description': 'C3', 'steps': [{'action': 'CheckDuration', 'signal': 'CSW_Stats_S', 'value': [2, 3, 4, 5], 'duration': 2.0}]}]
