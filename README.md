## Canoe DSL → JSON Converter

Parse human-friendly test DSL into structured JSON test cases.

### Quick start

1) Example DSL at `examples/TC-001.dsl`.

2) Convert to JSON:

```bash
python -m dsl_parser.cli examples/TC-001.dsl -o examples/TC-001.json
```

3) Options:
- `--event-timeout-ms` default timeout for `after EventName` when not specified (ms).

### DSL highlights
- Sections: `[SET]` and `[CHECK]` after `CASE:` and optional `META:`.
- SET: `Sx: set SignalA = 1 within 200ms [then CHECK C1,C2]`
- CHECK: `Cx: check SignalX == 1 window 0..1500ms [count >= 1] [after 100ms | after EventReady@500ms]`
- Assertions: `== v` | `in {a,b}` | `in a..b`
- Durations: `200ms`, `2s`; default `ms` if unit omitted.

### Output JSON shape
- `steps`: `{type: 'set'|'check', ...}`
- `flow`: resolved execution order (inline checks are inserted after their SET)
- `phase_order`: default phase order when no inline checks are used

## CANoe Controller (COM)

Minimal controller to operate measurement and read/write variables, assuming CANoe lifecycle is managed externally (e.g., Simulink).

### Usage

```python
from canoe_control import create_controller

ctl = create_controller()  # or create_controller("dummy") for CI
ctl.start_measurement()
ctl.write_environment_variable("MyEnv", 1)
val = ctl.read_system_variable("MyNs.SubNs.MyVar")
ctl.stop_measurement()
```


# BEV+GPS to OpenDRIVE (XODR) Converter

This project converts ego-centric BEV lane perception and GPS trajectory data into an OpenDRIVE (XODR) road description suitable for VTD simulations.

## Data assumptions
- BEV data is ego-centric with forward x-axis, left y-axis, in meters, valid up to 150 m ahead.
- Each BEV frame includes lane lines with IDs and polylines, and optional crosswalk (zebra) detections.
- GPS data includes timestamp, latitude, longitude, heading (degrees, yaw CW from North), and optionally speed (m/s).
- Camera occlusion is ignored (assume clear view).
- At red lights, geometry is static; only timestamps change.
- At intersections, lane lines may be missing; the ego trajectory continues through the gap until lanes reappear.

## Install
No external dependencies; uses Python 3 standard library.

## Run
```bash
python3 -m xodr_converter.cli \
  --gps /workspace/data/example/gps.csv \
  --bev /workspace/data/example/bev.json \
  --out /workspace/out/example.xodr
```

## Outputs
- An XODR file with a single road composed of lane sections, lane markings, zebra objects, and inferred traffic lights near stops.

## Notes
- Local ENU means: X axis points East, Y axis points North, Z axis Up, with origin at the first GPS fix. We use a local tangent-plane approximation suitable for short trips. Ego points (x forward, y left) are rotated by GPS heading (yaw clockwise from North) into this ENU frame.
- Plan view (reference line) uses a parametric cubic polynomial (paramPoly3) fitted to the trajectory, with straight-line degenerate cubic when needed.
- Junctions: When BEV indicates gaps at intersections, the trajectory is split and represented as multiple roads. Each connection through an intersection is modeled as a separate connecting road, and a junction element links incoming and connecting roads.