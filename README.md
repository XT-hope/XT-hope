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
本仓库主要功能（XODR 转换）不依赖第三方库；如果你要使用 DBC->CANoe 系统变量 XML 生成功能，需要安装 `cantools`：

```bash
python3 -m pip install -r requirements.txt
```

## Run
```bash
python3 -m xodr_converter.cli \
  --gps /workspace/data/example/gps.csv \
  --bev /workspace/data/example/bev.json \
  --out /workspace/out/example.xodr
```

## DBC -> CANoe 系统变量 XML

脚本：`dbc_to_canoe_sysvars.py`

### 示例（使用仓库内置的最小 DBC）

```bash
python3 /workspace/dbc_to_canoe_sysvars.py \
  --dbc /workspace/data/example/example.dbc \
  --out /workspace/out/example.vsysvar \
  --root-namespace DBC
```

### 常用参数

- `--format vector-vsysvar|generic`: 默认 `vector-vsysvar`，若你的 CANoe 导入对 schema 更严格可先试 `generic`
- `--name-pattern "{signal}"`：变量名模式，支持 `{message}` `{signal}` `{frame_id}`
- `--no-group-by-message`：不按 message 分组（否则默认层级为 `DBC/<Message>/<Signal>`）

## Outputs
- An XODR file with a single road composed of lane sections, lane markings, zebra objects, and inferred traffic lights near stops.

## Notes
- Local ENU means: X axis points East, Y axis points North, Z axis Up, with origin at the first GPS fix. We use a local tangent-plane approximation suitable for short trips. Ego points (x forward, y left) are rotated by GPS heading (yaw clockwise from North) into this ENU frame.
- Plan view (reference line) uses a parametric cubic polynomial (paramPoly3) fitted to the trajectory, with straight-line degenerate cubic when needed.
- Junctions: When BEV indicates gaps at intersections, the trajectory is split and represented as multiple roads. Each connection through an intersection is modeled as a separate connecting road, and a junction element links incoming and connecting roads.