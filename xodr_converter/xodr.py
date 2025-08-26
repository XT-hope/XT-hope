from __future__ import annotations
from typing import List, Tuple
from dataclasses import dataclass
from xml.etree import ElementTree as ET
import math


@dataclass
class LaneConfig:
	num_lanes: int = 1
	lane_width_m: float = 3.5
	mark_type: str = "broken"


class OpenDriveBuilder:
	def build(self, trajectory_xy: List[Tuple[float, float]], lane_cfg: LaneConfig, signals_s: List[float], zebras_xy_list: List[List[Tuple[float, float]]]) -> ET.Element:
		root = ET.Element("OpenDRIVE")
		header = ET.SubElement(root, "header")
		header.attrib.update({
			"revMajor": "1", "revMinor": "6", "name": "generated", "version": "1.6",
			"date": "2025-01-01T00:00:00Z", "north": "0", "south": "0", "east": "0", "west": "0",
		})
		road = ET.SubElement(root, "road", id="1", name="road_1", length=f"{self._compute_length(trajectory_xy):.3f}", junction="-1")
		plan = ET.SubElement(road, "planView")
		self._emit_plan_view_param_poly3(plan, trajectory_xy)
		lanes = ET.SubElement(road, "lanes")
		lane_section = ET.SubElement(lanes, "laneSection", s="0.000")
		center = ET.SubElement(lane_section, "center")
		ET.SubElement(center, "lane", id="0", type="none", level="false")
		right = ET.SubElement(lane_section, "right")
		for i in range(lane_cfg.num_lanes):
			lane = ET.SubElement(right, "lane", id=f"{-1 - i}", type="driving", level="false")
			ET.SubElement(lane, "width", sOffset="0.000", a=f"{lane_cfg.lane_width_m:.3f}", b="0", c="0", d="0")
			ET.SubElement(lane, "roadMark", sOffset="0.000", type=lane_cfg.mark_type, weight="standard", color="standard", material="standard", width="0.13")
		if signals_s:
			signals = ET.SubElement(road, "signals")
			for idx, s_pos in enumerate(signals_s):
				ET.SubElement(signals, "signal", id=str(idx+1), s=f"{s_pos:.3f}", t="0.0", name=f"tl_{idx+1}", type="1000001", subtype="1", country="", dynamic="yes", orientation="+")
		if zebras_xy_list:
			objects = ET.SubElement(road, "objects")
			for j, polygon in enumerate(zebras_xy_list):
				obj = ET.SubElement(objects, "object", id=str(j+1), name=f"zebra_{j+1}", s="0.0", t="0.0", zOffset="0.0", hdg="0.0", roll="0.0", pitch="0.0", orientation="+", type="crosswalk")
				outline = ET.SubElement(obj, "outline")
				for vx, vy in polygon:
					ET.SubElement(outline, "cornerLocal", u="0.0", v="0.0", z="0.0", height="0.0", x=f"{vx:.3f}", y=f"{vy:.3f}")
		return root

	def build_network(self, segments: List[Tuple[List[Tuple[float, float]], bool, float]], lane_cfg: LaneConfig, signals_s_global: List[float], zebras_xy_list: List[List[Tuple[float, float]]]) -> ET.Element:
		"""Build an OpenDRIVE with multiple roads split at junction gaps.
		segments: list of (trajectory_xy, is_connecting, start_s_global)
		"""
		root = ET.Element("OpenDRIVE")
		header = ET.SubElement(root, "header")
		header.attrib.update({
			"revMajor": "1", "revMinor": "6", "name": "generated", "version": "1.6",
			"date": "2025-01-01T00:00:00Z", "north": "0", "south": "0", "east": "0", "west": "0",
		})
		roads: List[ET.Element] = []
		road_ids: List[str] = []
		road_lengths: List[float] = []
		for idx, (traj, is_conn, start_s) in enumerate(segments):
			length = self._compute_length(traj)
			road_elem = ET.SubElement(root, "road", id=str(idx+1), name=("conn_" if is_conn else "road_") + str(idx+1), length=f"{length:.3f}", junction=("1" if is_conn else "-1"))
			plan = ET.SubElement(road_elem, "planView")
			self._emit_plan_view_param_poly3(plan, traj)
			lanes = ET.SubElement(road_elem, "lanes")
			lane_section = ET.SubElement(lanes, "laneSection", s="0.000")
			center = ET.SubElement(lane_section, "center")
			ET.SubElement(center, "lane", id="0", type="none", level="false")
			right = ET.SubElement(lane_section, "right")
			for i in range(lane_cfg.num_lanes):
				lane = ET.SubElement(right, "lane", id=f"{-1 - i}", type="driving", level="false")
				ET.SubElement(lane, "width", sOffset="0.000", a=f"{lane_cfg.lane_width_m:.3f}", b="0", c="0", d="0")
				ET.SubElement(lane, "roadMark", sOffset="0.000", type=lane_cfg.mark_type, weight="standard", color="standard", material="standard", width="0.13")
			roads.append(road_elem)
			road_ids.append(str(idx+1))
			road_lengths.append(length)
		# Link roads and create a simple junction if any connecting segment exists
		if roads:
			for i in range(len(roads) - 1):
				link = ET.SubElement(roads[i], "link")
				ET.SubElement(link, "successor", elementType="road", elementId=road_ids[i+1], contactPoint="start")
				plink = ET.SubElement(roads[i+1], "link")
				ET.SubElement(plink, "predecessor", elementType="road", elementId=road_ids[i], contactPoint="end")
			# Junction element (single) connecting first connecting road if present
			any_conn = any(seg[1] for seg in segments)
			if any_conn:
				junc = ET.SubElement(root, "junction", id="1", name="j1")
				for i, (_, is_conn, _) in enumerate(segments):
					if is_conn and i > 0:
						ET.SubElement(junc, "connection", id=str(i), incomingRoad=road_ids[i-1], connectingRoad=road_ids[i], contactPoint="end")
		# Minimal signals: assign to the first road segment by local s offset
		if signals_s_global and roads:
			signals = ET.SubElement(roads[0], "signals")
			for idx, s_pos in enumerate(signals_s_global):
				ET.SubElement(signals, "signal", id=str(idx+1), s=f"{s_pos:.3f}", t="0.0", name=f"tl_{idx+1}", type="1000001", subtype="1", country="", dynamic="yes", orientation="+")
		# Objects: attach to first road for now
		if zebras_xy_list and roads:
			objects = ET.SubElement(roads[0], "objects")
			for j, polygon in enumerate(zebras_xy_list):
				obj = ET.SubElement(objects, "object", id=str(j+1), name=f"zebra_{j+1}", s="0.0", t="0.0", zOffset="0.0", hdg="0.0", roll="0.0", pitch="0.0", orientation="+", type="crosswalk")
				outline = ET.SubElement(obj, "outline")
				for vx, vy in polygon:
					ET.SubElement(outline, "cornerLocal", u="0.0", v="0.0", z="0.0", height="0.0", x=f"{vx:.3f}", y=f"{vy:.3f}")
		return root

	@staticmethod
	def _compute_length(trajectory_xy: List[Tuple[float, float]]) -> float:
		total = 0.0
		for i in range(1, len(trajectory_xy)):
			dx = trajectory_xy[i][0] - trajectory_xy[i-1][0]
			dy = trajectory_xy[i][1] - trajectory_xy[i-1][1]
			total += math.hypot(dx, dy)
		return total

	def _emit_plan_view(self, plan_elem, trajectory_xy: List[Tuple[float, float]]) -> None:
		if not trajectory_xy:
			return
		s = 0.0
		for i in range(1, len(trajectory_xy)):
			x0, y0 = trajectory_xy[i-1]
			x1, y1 = trajectory_xy[i]
			ds = math.hypot(x1-x0, y1-y0)
			geom = ET.SubElement(plan_elem, "geometry", s=f"{s:.3f}", x=f"{x0:.3f}", y=f"{y0:.3f}", hdg=f"{self._heading(x0,y0,x1,y1):.6f}", length=f"{ds:.3f}")
			ET.SubElement(geom, "line")
			s += ds

	def _emit_plan_view_param_poly3(self, plan_elem, trajectory_xy: List[Tuple[float, float]]) -> None:
		"""Emit a single paramPoly3 segment fitted to the trajectory. Falls back to degenerate straight param poly when necessary."""
		if len(trajectory_xy) < 2:
			return
		# Compute cumulative distances and start heading
		s_vals = [0.0]
		for i in range(1, len(trajectory_xy)):
			ds = math.hypot(trajectory_xy[i][0]-trajectory_xy[i-1][0], trajectory_xy[i][1]-trajectory_xy[i-1][1])
			s_vals.append(s_vals[-1] + ds)
		length = s_vals[-1]
		if length <= 1e-6:
			# Degenerate zero-length
			x0, y0 = trajectory_xy[0]
			geom = ET.SubElement(plan_elem, "geometry", s="0.000", x=f"{x0:.3f}", y=f"{y0:.3f}", hdg="0.000000", length="0.000")
			ET.SubElement(geom, "paramPoly3", aU="0.0", bU="0.0", cU="0.0", dU="0.0", aV="0.0", bV="0.0", cV="0.0", dV="0.0", pRange="normalized")
			return
		x0, y0 = trajectory_xy[0]
		x1, y1 = trajectory_xy[1]
		hdg0 = self._heading(x0, y0, x1, y1)
		cos_h = math.cos(hdg0)
		sin_h = math.sin(hdg0)
		# If only two points, emit straight degenerate cubic
		if len(trajectory_xy) == 2:
			geom = ET.SubElement(plan_elem, "geometry", s="0.000", x=f"{x0:.3f}", y=f"{y0:.3f}", hdg=f"{hdg0:.6f}", length=f"{length:.3f}")
			ET.SubElement(geom, "paramPoly3", aU="0.0", bU=f"{length:.8f}", cU="0.0", dU="0.0", aV="0.0", bV="0.0", cV="0.0", dV="0.0", pRange="normalized")
			return
		# Normalize parameter p in [0,1]
		p_vals = [sv/length for sv in s_vals]
		u_vals: List[float] = []
		v_vals: List[float] = []
		for (x, y) in trajectory_xy:
			dx = x - x0
			dy = y - y0
			u =  cos_h * dx + sin_h * dy
			v = -sin_h * dx + cos_h * dy
			u_vals.append(u)
			v_vals.append(v)
		# Fit cubic a + b p + c p^2 + d p^3
		try:
			aU, bU, cU, dU = self._fit_cubic_least_squares(p_vals, u_vals)
			aV, bV, cV, dV = self._fit_cubic_least_squares(p_vals, v_vals)
		except Exception:
			# Emit straight degenerate cubic
			geom = ET.SubElement(plan_elem, "geometry", s="0.000", x=f"{x0:.3f}", y=f"{y0:.3f}", hdg=f"{hdg0:.6f}", length=f"{length:.3f}")
			ET.SubElement(geom, "paramPoly3", aU="0.0", bU=f"{length:.8f}", cU="0.0", dU="0.0", aV="0.0", bV="0.0", cV="0.0", dV="0.0", pRange="normalized")
			return
		geom = ET.SubElement(plan_elem, "geometry", s="0.000", x=f"{x0:.3f}", y=f"{y0:.3f}", hdg=f"{hdg0:.6f}", length=f"{length:.3f}")
		ET.SubElement(geom, "paramPoly3", aU=f"{aU:.8f}", bU=f"{bU:.8f}", cU=f"{cU:.8f}", dU=f"{dU:.8f}", aV=f"{aV:.8f}", bV=f"{bV:.8f}", cV=f"{cV:.8f}", dV=f"{dV:.8f}", pRange="normalized")

	@staticmethod
	def _heading(x0: float, y0: float, x1: float, y1: float) -> float:
		return math.atan2(y1 - y0, x1 - x0)

	@staticmethod
	def _fit_cubic_least_squares(p_vals: List[float], y_vals: List[float]) -> Tuple[float, float, float, float]:
		"""Solve min||A c - y||^2 with A=[1 p p^2 p^3] via normal equations. Returns (a,b,c,d)."""
		n = len(p_vals)
		if n < 4:
			# fall back to linear by padding zeros
			p_vals = p_vals + [1.0]*(4-n)
			y_vals = y_vals + [y_vals[-1]]*(4-n)
		# Compute sums s_k = sum p^k
		s = [0.0]*7
		sp = [0.0]*4
		for p, y in zip(p_vals, y_vals):
			pk = 1.0
			for k in range(7):
				s[k] += pk
				pk *= p
			# y* p^k
			pk = 1.0
			for k in range(4):
				sp[k] += y * pk
				pk *= p
		# Normal matrix (4x4)
		M = [
			[s[0], s[1], s[2], s[3]],
			[s[1], s[2], s[3], s[4]],
			[s[2], s[3], s[4], s[5]],
			[s[3], s[4], s[5], s[6]],
		]
		b = [sp[0], sp[1], sp[2], sp[3]]
		# Solve M c = b
		coeffs = OpenDriveBuilder._solve_4x4(M, b)
		return coeffs[0], coeffs[1], coeffs[2], coeffs[3]

	@staticmethod
	def _solve_4x4(M: List[List[float]], b: List[float]) -> List[float]:
		# Gaussian elimination with partial pivoting for 4x4
		A = [row[:] for row in M]
		xb = b[:]
		n = 4
		for i in range(n):
			# pivot
			pivot = i
			maxv = abs(A[i][i])
			for r in range(i+1, n):
				if abs(A[r][i]) > maxv:
					maxv = abs(A[r][i])
					pivot = r
			if maxv < 1e-12:
				raise ValueError("Singular matrix in fit")
			if pivot != i:
				A[i], A[pivot] = A[pivot], A[i]
				xb[i], xb[pivot] = xb[pivot], xb[i]
			# normalize
			diag = A[i][i]
			for c in range(i, n):
				A[i][c] /= diag
			xb[i] /= diag
			# eliminate
			for r in range(n):
				if r == i:
					continue
				factor = A[r][i]
				for c in range(i, n):
					A[r][c] -= factor * A[i][c]
				xb[r] -= factor * xb[i]
		return xb