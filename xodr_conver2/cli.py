from __future__ import annotations
import argparse
import os
from typing import List, Tuple
from xml.etree import ElementTree as ET
from .loaders import load_gps_csv, load_bev_json
from .stitch import compute_poses_enu, compute_path_length_s, detect_stops, detect_intersection_gaps, simplify_trajectory, split_poses_by_gaps
from .coord import CoordinateConverter
from .types import BEVFrame
from .xodr import OpenDriveBuilder, LaneConfig


def match_bev_to_gps(bev: List[BEVFrame], poses_ts: List[float]) -> List[int]:
	# For each BEV frame ts, find nearest GPS pose index
	idxs: List[int] = []
	j = 0
	for bf in bev:
		best = 0
		best_dt = float('inf')
		for i, ts in enumerate(poses_ts[j:]):
			dt = abs(ts - bf.ts)
			if dt < best_dt:
				best_dt = dt
				best = j + i
			else:
				break
		j = best
		idxs.append(best)
	return idxs


def main():
	ap = argparse.ArgumentParser(description="Convert BEV+GPS to OpenDRIVE XODR")
	ap.add_argument("--gps", required=True, help="Path to GPS CSV")
	ap.add_argument("--bev", required=True, help="Path to BEV JSON")
	ap.add_argument("--out", required=True, help="Output XODR path")
	args = ap.parse_args()

	gps = load_gps_csv(args.gps)
	bev = load_bev_json(args.bev)
	poses, ref = compute_poses_enu(gps)
	s_vals = compute_path_length_s(poses)
	stop_segments = detect_stops(gps, poses, s_vals)
	gap_segments = detect_intersection_gaps(bev, poses, s_vals)

	# Split trajectory into segments by gaps and simplify each segment
	seg_defs = split_poses_by_gaps(poses, s_vals, gap_segments)
	segments_xy: List[Tuple[List[Tuple[float, float]], bool, float]] = []
	for seg_poses, is_conn, start_s in seg_defs:
		seg_xy = simplify_trajectory(seg_poses, tolerance_m=0.5)
		segments_xy.append((seg_xy, is_conn, start_s))
	builder = OpenDriveBuilder()

	# Default to 3 lanes per side for dual-direction arterial unless overridden later
	lane_cfg = LaneConfig(num_lanes_left=3, num_lanes_right=3, lane_width_m=3.5, mark_type="broken")
	signals_s = [seg.s_at_start for seg in stop_segments]
	# Crosswalks: transform ego polygons at matched frames into ENU approx using pose heading
	poses_ts = [p.ts for p in poses]
	match_idxs = match_bev_to_gps(bev, poses_ts)
	zebra_polys_world: List[List[Tuple[float, float]]] = []
	for bf, idx in zip(bev, match_idxs):
		pose = poses[idx]
		for zebra in bf.zebras:
			poly_world = []
			for x_ego, y_ego in zebra.polygon_xy:
				xw, yw = CoordinateConverter.ego_to_enu(x_ego, y_ego, pose.x_e, pose.y_n, pose.heading_deg)
				poly_world.append((xw, yw))
			zebra_polys_world.append(poly_world)

	root = builder.build_network(segments_xy, lane_cfg, signals_s, zebra_polys_world)
	os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
	ET.ElementTree(root).write(args.out, encoding="utf-8", xml_declaration=True)


if __name__ == "__main__":
	main()