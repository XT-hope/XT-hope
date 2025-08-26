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
- Coordinate system is local ENU relative to the first GPS fix (spherical Earth approximation). Ego-frame points are rotated by GPS heading into ENU.
- Intersections are represented by lane sections with lane marks set to `none` where BEV is missing.