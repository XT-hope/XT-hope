CASE: OrinN_MR25_CSW_022_004
META: test_point=弯中R50_超出安全过弯车速38km/h priority=P0-高 owner=auto scenario_id=48 scenario_name=Csw_Straight200_50RadiusCurve_YellowSolidLine_40kph_InCurve.mat

[SET]
S1: set sys::FunctionSwitch::CSW_Enable_S=0x1
S2: set sys::DriverAction::gear=0x4 wait 500ms

[CHECK]
C1: check sig::CAN 1::ADC_0x29C::CSW_Stats_S==3 timeoutOfCheck 5s
