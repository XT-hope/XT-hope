# -*- coding: utf-8 -*-
__name__ = 'Demo_S4_And_KeepDynamic'

# META（原 DSL）
# scenario_id=1

URLmapping = ['EPS_SteerWheelAg', 'EPS_SteerWheelAgVld']

URLTests = [{'description': '初始化场景', 'steps': [{'action': 'SetScenario', 'scenario_id': 1}]},
 {'description': 'S4',
  'steps': [{'action': 'SetSysVar', 'namespace': 'simulink', 'value': 1, 'var_name': 'dynamic_disconnect'},
            {'action': 'SetSignal', 'signal': 'EPS_SteerWheelAg', 'value': 181},
            {'action': 'SetSignal', 'signal': 'EPS_SteerWheelAgVld', 'value': 1},
            {'action': 'Wait', 'wait_time': 0.3}]}]
