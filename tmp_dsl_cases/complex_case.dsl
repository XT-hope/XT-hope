CASE: Demo_KeepDynamic_ThenCheck
META: scenario_id=9 owner=auto

S1: set sys::FunctionSwitch::CSW_Enable_S wait 200ms then CHECK C1,C2
S2: set env::CAN 1::IPB_0x10C::VDC_Fault=0x1 keep_dynamic false

C1: check sig::CAN 1::ADC_0x29C::CSW_Stats_S ==3 timeoutOfCheck 1500ms wait 200ms
C2: check sig::CAN 1::ADC_0x29C::CSW_Stats_S in {2,3} timeoutOfCheck 1000ms
C3: check sig::CAN 1::ADC_0x29C::CSW_Stats_S in 2..5 checkInTime 2s
