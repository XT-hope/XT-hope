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

## DBC to CANoe system variables
Convert one or more DBC files into a single CANoe `.vsysvar` XML file:

```bash
python3 -m xodr_converter.dbc_to_vsysvar \
  --dbc ControlCAN=/path/to/control.dbc \
  --dbc ChassisCAN=/path/to/chassis.dbc \
  --out /path/to/vehicle.vsysvar
```

Each DBC becomes one namespace. Each DBC message becomes one struct definition plus one struct variable. Each signal creates `_Pv`, `_Rv`, `_Factor`, and `_Offset` struct members.

## Notes
- Local ENU means: X axis points East, Y axis points North, Z axis Up, with origin at the first GPS fix. We use a local tangent-plane approximation suitable for short trips. Ego points (x forward, y left) are rotated by GPS heading (yaw clockwise from North) into this ENU frame.
- Plan view (reference line) uses a parametric cubic polynomial (paramPoly3) fitted to the trajectory, with straight-line degenerate cubic when needed.
- Junctions: When BEV indicates gaps at intersections, the trajectory is split and represented as multiple roads. Each connection through an intersection is modeled as a separate connecting road, and a junction element links incoming and connecting roads.