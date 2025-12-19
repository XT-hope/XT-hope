CASE: Demo_S4_And_KeepDynamic
META: scenario_id=1

S4: set env::CAN 1::EPS_0x06D::EPS_SteerWheelAg=181 && env::CAN 1::EPS_0x06D::EPS_SteerWheelAgVld=0x1 keepDynamic false wait 300ms
