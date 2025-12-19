# -*- coding: utf-8 -*-
__name__ = 'OrinN_MR25_CSW_022_004'

# META（原 DSL）
# test_point=弯中R50_超出安全过弯车速38km/h
# priority=P0-高
# owner=auto
# scenario_id=48
# scenario_name=Csw_Straight200_50RadiusCurve_YellowSolidLine_40kph_InCurve.mat

URLmapping = ['CSW_Stats_S']

URLTests = [{'description': '初始化场景', 'steps': [{'action': 'SetScenario', 'scenario_id': 48}]},
 {'description': 'S1',
  'steps': [{'action': 'SetSysVar', 'namespace': 'FunctionSwitch', 'value': 1, 'var_name': 'CSW_Enable_S'}]},
 {'description': 'S2',
  'steps': [{'action': 'SetSysVar', 'namespace': 'DriverAction', 'value': 4, 'var_name': 'gear'},
            {'action': 'Wait', 'wait_time': 0.5}]},
 {'description': 'C1', 'steps': [{'action': 'CheckSignal', 'signal': 'CSW_Stats_S', 'timeout': 5.0, 'value': 3}]}]
