# -*- coding: utf-8 -*-
__name__ = 'Demo_KeepDynamic_ThenCheck'

# META（原 DSL）
# scenario_id=9
# owner=auto

URLmapping = ['CSW_Stats_S', 'VDC_Fault']

URLTests = [{'description': '初始化场景', 'steps': [{'action': 'SetScenario', 'scenario_id': 9}]},
 {'description': 'S1',
  'steps': [{'action': 'SetSysVar', 'namespace': 'FunctionSwitch', 'value': 1, 'var_name': 'CSW_Enable_S'},
            {'action': 'Wait', 'wait_time': 0.2}]},
 {'description': 'C1',
  'steps': [{'action': 'CheckSignal', 'signal': 'CSW_Stats_S', 'timeout': 1.5, 'value': 3, 'wait_time': 0.2}]},
 {'description': 'C2',
  'steps': [{'action': 'CheckSignal', 'operator': 'in', 'signal': 'CSW_Stats_S', 'timeout': 1.0, 'value': [2, 3]}]},
 {'description': 'S2',
  'steps': [{'action': 'SetSysVar', 'namespace': 'simulink', 'value': 1, 'var_name': 'dynamic_disconnect'},
            {'action': 'SetSignal', 'signal': 'VDC_Fault', 'value': 1}]},
 {'description': 'C3',
  'steps': [{'action': 'CheckDuration',
             'duration': 2.0,
             'operator': 'range',
             'signal': 'CSW_Stats_S',
             'value': {'max': 5, 'min': 2}}]}]
