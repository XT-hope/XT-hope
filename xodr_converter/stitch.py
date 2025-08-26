from __future__ import annotations
from typing import List, Tuple
import math
from dataclasses import dataclass
from .types import GPSRecord, BEVFrame, EgoPoseENU
from .coord import CoordinateConverter, ReferenceOrigin


@dataclass
class StopSegment:
	start_ts: float
	end_ts: float
	s_at_start: float
	signal_hint: bool = True


@dataclass
class IntersectionGap:
	start_ts: float
	end_ts: float
	s_start: float
	s_end: float


def compute_poses_enu(gps: List[GPSRecord]) -> Tuple[List[EgoPoseENU], ReferenceOrigin]:
	if not gps:
		raise ValueError("Empty GPS list")
	ref = ReferenceOrigin(lat0=gps[0].lat, lon0=gps[0].lon)
	conv = CoordinateConverter(ref)
	poses: List[EgoPoseENU] = []
	for rec in gps:
		x, y = conv.wgs84_to_enu(rec.lon, rec.lat)
		poses.append(EgoPoseENU(ts=rec.ts, x_e=x, y_n=y, heading_deg=rec.heading_deg))
	return poses, ref


def compute_path_length_s(poses: List[EgoPoseENU]) -> List[float]:
	s_vals: List[float] = [0.0]
	for i in range(1, len(poses)):
		dx = poses[i].x_e - poses[i-1].x_e
		dy = poses[i].y_n - poses[i-1].y_n
		ds = math.hypot(dx, dy)
		s_vals.append(s_vals[-1] + ds)
	return s_vals


def detect_stops(gps: List[GPSRecord], poses: List[EgoPoseENU], s_vals: List[float], speed_threshold: float = 0.2, min_duration_s: float = 3.0) -> List[StopSegment]:
	stops: List[StopSegment] = []
	in_stop = False
	start_idx = 0
	for i, rec in enumerate(gps):
		spd = rec.speed_mps if rec.speed_mps is not None else None
		if spd is not None and spd <= speed_threshold:
			if not in_stop:
				in_stop = True
				start_idx = i
		else:
			if in_stop:
				in_stop = False
				dur = gps[i-1].ts - gps[start_idx].ts
				if dur >= min_duration_s:
					stops.append(StopSegment(start_ts=gps[start_idx].ts, end_ts=gps[i-1].ts, s_at_start=s_vals[start_idx]))
	if in_stop:
		dur = gps[-1].ts - gps[start_idx].ts
		if dur >= min_duration_s:
			stops.append(StopSegment(start_ts=gps[start_idx].ts, end_ts=gps[-1].ts, s_at_start=s_vals[start_idx]))
	return stops


def detect_intersection_gaps(bev_frames: List[BEVFrame], poses: List[EgoPoseENU], s_vals: List[float], min_gap_duration_s: float = 1.0) -> List[IntersectionGap]:
	gaps: List[IntersectionGap] = []
	in_gap = False
	start_i = 0
	for i, fr in enumerate(bev_frames):
		has_lanes = len(fr.lane_lines) > 0
		if not has_lanes:
			if not in_gap:
				in_gap = True
				start_i = i
		else:
			if in_gap:
				in_gap = False
				dt = bev_frames[i-1].ts - bev_frames[start_i].ts
				if dt >= min_gap_duration_s:
					gaps.append(IntersectionGap(start_ts=bev_frames[start_i].ts, end_ts=bev_frames[i-1].ts, s_start=s_vals[start_i], s_end=s_vals[i-1]))
	if in_gap and bev_frames:
		dt = bev_frames[-1].ts - bev_frames[start_i].ts
		if dt >= min_gap_duration_s:
			gaps.append(IntersectionGap(start_ts=bev_frames[start_i].ts, end_ts=bev_frames[-1].ts, s_start=s_vals[start_i], s_end=s_vals[-1]))
	return gaps


def _point_line_distance(p: Tuple[float,float], a: Tuple[float,float], b: Tuple[float,float]) -> float:
	# Distance from point p to line segment ab
	(ax, ay), (bx, by), (px, py) = a, b, p
	abx, aby = bx - ax, by - ay
	apx, apy = px - ax, py - ay
	ab_len2 = abx*abx + aby*aby
	if ab_len2 == 0:
		return math.hypot(apx, apy)
	t = max(0.0, min(1.0, (apx*abx + apy*aby) / ab_len2))
	nx, ny = ax + t*abx, ay + t*aby
	return math.hypot(px - nx, py - ny)


def _douglas_peucker(points: List[Tuple[float,float]], epsilon: float) -> List[Tuple[float,float]]:
	if len(points) <= 2:
		return points[:]
	max_dist = -1.0
	index = 0
	for i in range(1, len(points)-1):
		d = _point_line_distance(points[i], points[0], points[-1])
		if d > max_dist:
			index = i
			max_dist = d
	if max_dist > epsilon:
		res1 = _douglas_peucker(points[: index+1], epsilon)
		res2 = _douglas_peucker(points[index: ], epsilon)
		return res1[:-1] + res2
	else:
		return [points[0], points[-1]]


def simplify_trajectory(poses: List[EgoPoseENU], tolerance_m: float = 0.3) -> List[Tuple[float, float]]:
	coords = [(p.x_e, p.y_n) for p in poses]
	if not coords:
		return []
	return _douglas_peucker(coords, tolerance_m)