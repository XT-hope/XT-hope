CASE: OrinN_MR25_CSW_022_004
META: test_point=弯中R50_超出安全过弯车速38km/h priority=P0-高 owner=auto scenario_id=48 scenario_name=Csw_Straight200_50RadiusCurve_YellowSolidLine_40kph_InCurve.mat
S1: set sys::FunctionSwitch::CSW_Enable_S && set env::CAN 1::IPB_0x10C::VDC_Fault=0x1 wait 200ms then CHECK C1,C2
S2: set sys::FunctionSwitch::CSW_Enable_S keep_dynamic false then CHECK C1
S3: set sys::FunctionSwitch::CSW_Enable_S=0x1
C1: check sig::CAN 1::ADC_0x29C::CSW_Stats_S ==3 timeoutOfCheck 1500ms wait 200ms
C2: check sig::CAN 1::ADC_0x29C::CSW_Stats_S in {2,3} timeoutOfCheck 1000ms
C3: check sig::CAN 1::ADC_0x29C::CSW_Stats_S in 2..5 checkInTime 2s
