CASE: TC-001 SetAndCheckSignals
META: priority=P1 owner=QA requirement=REQ-123

[SET]
S1: set SignalA = 1 within 200ms
S2: set SignalB = 0 && SignalD = 2 within 100ms then CHECK C1
S3: set SignalC = 3

[CHECK]
C1: check SignalX == 1 timeoutOfCheck 1500ms after 100ms count >= 1
C2: check SignalY in {2,3} timeoutOfCheck 1000ms after 100ms count == 2

