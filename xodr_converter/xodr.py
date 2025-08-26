from __future__ import annotations
from typing import List, Tuple
from dataclasses import dataclass
from xml.etree import ElementTree as ET
import math


@dataclass
class LaneConfig:
	# Backward-compatible: if num_lanes_left/right are zero, fall back to num_lanes (legacy right-only with negative ids)
	num_lanes: int = 1
	num_lanes_left: int = 0
	num_lanes_right: int = 0
	lane_width_m: float = 3.5
	mark_type: str = "broken"
	# If true and only one side is provided (>0), mirror the other side with the same count
	mirror_missing_side: bool = True


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
		# Determine lane counts per side
		n_left = lane_cfg.num_lanes_left if lane_cfg.num_lanes_left is not None else 0
		n_right = lane_cfg.num_lanes_right if lane_cfg.num_lanes_right is not None else 0
		if (n_left <= 0 and n_right <= 0) and lane_cfg.num_lanes > 0:
			# fallback: right-only using legacy field
			n_right = lane_cfg.num_lanes
		# mirror if only one side present
		if lane_cfg.mirror_missing_side:
			if n_left > 0 and n_right <= 0:
				n_right = n_left
			elif n_right > 0 and n_left <= 0:
				n_left = n_right
		# Left side (positive ids)
		if n_left > 0:
			left = ET.SubElement(lane_section, "left")
			for i in range(n_left):
				lane = ET.SubElement(left, "lane", id=f"{1 + i}", type="driving", level="false")
				ET.SubElement(lane, "width", sOffset="0.000", a=f"{lane_cfg.lane_width_m:.3f}", b="0", c="0", d="0")
				ET.SubElement(lane, "roadMark", sOffset="0.000", type=lane_cfg.mark_type, weight="standard", color="standard", material="standard", width="0.13")
		# Right side (negative ids)
		if n_right > 0:
			right = ET.SubElement(lane_section, "right")
			for i in range(n_right):
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
		- A sequence [incoming, connecting=True, outgoing] will be wired through a junction with laneLinks
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
			# For connecting segments, we will consider emitting line-arc-line geometry based on adjacent roads
			self._emit_plan_view_param_poly3(plan, traj)
			lanes = ET.SubElement(road_elem, "lanes")
			lane_section = ET.SubElement(lanes, "laneSection", s="0.000")
			center = ET.SubElement(lane_section, "center")
			ET.SubElement(center, "lane", id="0", type="none", level="false")
			# Determine lane counts per side
			n_left = lane_cfg.num_lanes_left if lane_cfg.num_lanes_left is not None else 0
			n_right = lane_cfg.num_lanes_right if lane_cfg.num_lanes_right is not None else 0
			if (n_left <= 0 and n_right <= 0) and lane_cfg.num_lanes > 0:
				n_right = lane_cfg.num_lanes
			# For connecting segments, default to single right-side lane unless explicitly specified
			if is_conn:
				n_left = 0
				n_right = max(1, n_right if n_left > 0 or n_right > 0 else 1)
			# mirror if only one side present (non-connecting only)
			if lane_cfg.mirror_missing_side and not is_conn:
				if n_left > 0 and n_right <= 0:
					n_right = n_left
				elif n_right > 0 and n_left <= 0:
					n_left = n_right
			# Left side
			if n_left > 0:
				left = ET.SubElement(lane_section, "left")
				for i in range(n_left):
					lane = ET.SubElement(left, "lane", id=f"{1 + i}", type="driving", level="false")
					ET.SubElement(lane, "width", sOffset="0.000", a=f"{lane_cfg.lane_width_m:.3f}", b="0", c="0", d="0")
					ET.SubElement(lane, "roadMark", sOffset="0.000", type=lane_cfg.mark_type, weight="standard", color="standard", material="standard", width="0.13")
			# Right side
			if n_right > 0:
				right = ET.SubElement(lane_section, "right")
				for i in range(n_right):
					lane = ET.SubElement(right, "lane", id=f"{-1 - i}", type="driving", level="false")
					ET.SubElement(lane, "width", sOffset="0.000", a=f"{lane_cfg.lane_width_m:.3f}", b="0", c="0", d="0")
					ET.SubElement(lane, "roadMark", sOffset="0.000", type=lane_cfg.mark_type, weight="standard", color="standard", material="standard", width="0.13")
			roads.append(road_elem)
			road_ids.append(str(idx+1))
			road_lengths.append(length)
		# Linking logic with optional junctions
		junc: ET.Element | None = None
		consumed = [False] * len(roads)
		for i in range(len(roads)):
			# Try to detect [incoming, connecting, outgoing]
			if i + 2 < len(roads):
				incoming_is_ok = True
				connecting_is_conn = segments[i+1][1]
				if connecting_is_conn:
					# create junction if needed
					if junc is None:
						junc = ET.SubElement(root, "junction", id="1", name="j1")
					# incoming -> junction at end
					link_in = ET.SubElement(roads[i], "link")
					ET.SubElement(link_in, "successor", elementType="junction", elementId="1", contactPoint="end")
					# connecting road predecessor/ successor
					link_conn = ET.SubElement(roads[i+1], "link")
					ET.SubElement(link_conn, "predecessor", elementType="road", elementId=road_ids[i], contactPoint="end")
					ET.SubElement(link_conn, "successor", elementType="road", elementId=road_ids[i+2], contactPoint="start")
					# outgoing road predecessor from junction at start
					link_out = ET.SubElement(roads[i+2], "link")
					ET.SubElement(link_out, "predecessor", elementType="junction", elementId="1", contactPoint="start")
					# Determine movement type based on heading delta
					mov = self._classify_movement(segments[i][0], segments[i+2][0])
					# junction connection with laneLinks (map based on lane responsibility policy)
					conn = ET.SubElement(junc, "connection", id=str(i+1), incomingRoad=road_ids[i], connectingRoad=road_ids[i+1], contactPoint="end")
					# Decide incoming lane ids to map
					in_right = lane_cfg.num_lanes_right if (lane_cfg.num_lanes_right and lane_cfg.num_lanes_right > 0) else (lane_cfg.num_lanes if lane_cfg.num_lanes > 0 else 1)
					from_ids = self._pick_incoming_lanes_for_movement(mov, in_right)
					# Connecting road right-side lane ids start at -1
					to_ids = ["-1"]
					# Emit laneLinks
					for k in range(min(len(from_ids), len(to_ids))):
						ET.SubElement(conn, "laneLink", _from=f"{from_ids[k]}", to=f"{to_ids[k]}")
					# Replace connecting geometry with line-arc-line when feasible
					try:
						self._rewrite_connecting_plan_line_arc_line(roads[i+1].find("planView"), segments[i][0], segments[i+2][0], mov)
					except Exception:
						pass
					consumed[i] = True
					consumed[i+1] = True
					consumed[i+2] = True
					continue
			# If not part of a junction triple, link sequentially when possible
			if not consumed[i]:
				if i + 1 < len(roads) and not segments[i+1][1]:
					link = ET.SubElement(roads[i], "link")
					ET.SubElement(link, "successor", elementType="road", elementId=road_ids[i+1], contactPoint="start")
					plink = ET.SubElement(roads[i+1], "link")
					ET.SubElement(plink, "predecessor", elementType="road", elementId=road_ids[i], contactPoint="end")
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
		x0, y0 = trajectory_xy[0]
		x1, y1 = trajectory_xy[-1]
		hdg0 = self._heading(trajectory_xy[0][0], trajectory_xy[0][1], trajectory_xy[1][0], trajectory_xy[1][1])
		cos_h = math.cos(hdg0)
		sin_h = math.sin(hdg0)
		# If only two points, emit straight degenerate cubic
		if len(trajectory_xy) == 2:
			geom = ET.SubElement(plan_elem, "geometry", s="0.000", x=f"{x0:.3f}", y=f"{y0:.3f}", hdg=f"{hdg0:.6f}", length=f"{length:.3f}")
			ET.SubElement(geom, "paramPoly3", aU="0.0", bU=f"{length:.8f}", cU="0.0", dU="0.0", aV="0.0", bV="0.0", cV="0.0", dV="0.0", pRange="normalized")
			return
		# Fit cubic in local param p in [0,1]
		p_vals = [s/length for s in s_vals]
		u_vals = []
		v_vals = []
		for (x, y) in trajectory_xy:
			dx = x - x0
			dy = y - y0
			u_vals.append(dx * cos_h + dy * sin_h)
			v_vals.append(-dx * sin_h + dy * cos_h)
		try:
			aU, bU, cU, dU = self._fit_cubic_least_squares(p_vals, u_vals)
			aV, bV, cV, dV = self._fit_cubic_least_squares(p_vals, v_vals)
		except Exception:
			# Emit straight degenerate cubic
			geom = ET.SubElement(plan_elem, "geometry", s="0.000", x=f"{x0:.3f}", y=f"{y0:.3f}", hdg=f"{hdg0:.6f}", length=f"{length:.3f}")
			ET.SubElement(geom, "paramPoly3", aU="0.0", bU=f"{length:.8f}", cU="0.0", dU="0.0", aV="0.0", bV="0.0", cV="0.0", dV="0.0", pRange="normalized")
			return
		geom = ET.SubElement(plan_elem, "geometry", s="0.000", x=f"{x0:.3f}", y=f"{y0:.3f}", hdg=f"{hdg0:.6f}", length=f"{length:.3f}")
		ET.SubElement(geom, "paramPoly3", aU=f"{aU:.8f}", bU=f"{bU*length:.8f}", cU=f"{cU*length*length:.8f}", dU=f"{dU*length*length*length:.8f}", aV=f"{aV:.8f}", bV=f"{bV*length:.8f}", cV=f"{cV*length*length:.8f}", dV=f"{dV*length*length*length:.8f}", pRange="normalized")

	@staticmethod
	def _heading(x0: float, y0: float, x1: float, y1: float) -> float:
		return math.atan2(y1 - y0, x1 - x0)

	@staticmethod
	def _normalize_angle(angle: float) -> float:
		# Normalize to [-pi, pi]
		a = (angle + math.pi) % (2.0 * math.pi) - math.pi
		return a

	def _classify_movement(self, incoming_xy: List[Tuple[float, float]], outgoing_xy: List[Tuple[float, float]]) -> str:
		"""Classify movement type: 'straight', 'left', or 'right' based on heading delta."""
		if len(incoming_xy) < 2 or len(outgoing_xy) < 2:
			return "straight"
		h_in = self._heading(incoming_xy[-2][0], incoming_xy[-2][1], incoming_xy[-1][0], incoming_xy[-1][1])
		h_out = self._heading(outgoing_xy[0][0], outgoing_xy[0][1], outgoing_xy[1][0], outgoing_xy[1][1])
		delta = self._normalize_angle(h_out - h_in)
		deg = abs(math.degrees(delta))
		if deg < 20.0:
			return "straight"
		return "left" if delta > 0.0 else "right"

	@staticmethod
	def _pick_incoming_lanes_for_movement(movement: str, num_right_lanes: int) -> List[str]:
		"""Pick incoming lane ids (negative) by policy: -1 rightmost curb, -2 middle, -3 inner near median."""
		if num_right_lanes >= 3:
			if movement == "right":
				return ["-1"]
			elif movement == "straight":
				return ["-2"]
			else:
				return ["-3"]
		elif num_right_lanes == 2:
			if movement == "left":
				return ["-2"]
			else:
				return ["-1"]
		else:
			return ["-1"]

	def _rewrite_connecting_plan_line_arc_line(self, plan_elem: ET.Element | None, incoming_xy: List[Tuple[float, float]], outgoing_xy: List[Tuple[float, float]], movement: str) -> None:
		"""Replace planView of a connecting road with line-arc-line geometry connecting lane-center endpoints.
		Uses a default radius per movement and ensures tangency to incoming/outgoing headings.
		"""
		if plan_elem is None:
			return
		if len(incoming_xy) < 2 or len(outgoing_xy) < 2:
			return
		# Determine radius by movement
		R = 15.0 if movement == "right" else (30.0 if movement == "left" else 80.0)
		p_in = incoming_xy[-1]
		p_in_prev = incoming_xy[-2]
		p_out = outgoing_xy[0]
		p_out_next = outgoing_xy[1]
		h_in = self._heading(p_in_prev[0], p_in_prev[1], p_in[0], p_in[1])
		h_out = self._heading(p_out[0], p_out[1], p_out_next[0], p_out_next[1])
		delta = self._normalize_angle(h_out - h_in)
		if abs(delta) < math.radians(5.0):
			# Near-straight: keep original
			return
		# Compute tangent offsets
		d = R * math.tan(abs(delta) / 2.0)
		ux_in = math.cos(h_in)
		uy_in = math.sin(h_in)
		ux_out = math.cos(h_out)
		uy_out = math.sin(h_out)
		T_in = (p_in[0] + ux_in * d, p_in[1] + uy_in * d)
		T_out = (p_out[0] - ux_out * d, p_out[1] - uy_out * d)
		# Build offset lines for center intersection
		sign = 1.0 if delta > 0.0 else -1.0
		n_in = (-uy_in * sign, ux_in * sign)
		n_out = (-uy_out * sign, ux_out * sign)
		P1 = (T_in[0] + n_in[0] * R, T_in[1] + n_in[1] * R)
		P2 = (T_out[0] + n_out[0] * R, T_out[1] + n_out[1] * R)
		# Solve P1 + u_in * t1 = P2 + u_out * t2
		den = ux_in * uy_out - uy_in * ux_out
		if abs(den) < 1e-6:
			return
		t1 = ((P2[0] - P1[0]) * uy_out - (P2[1] - P1[1]) * ux_out) / den
		C = (P1[0] + ux_in * t1, P1[1] + uy_in * t1)
		# Validate distances
		if abs(math.hypot(T_in[0]-C[0], T_in[1]-C[1]) - R) > 0.2 or abs(math.hypot(T_out[0]-C[0], T_out[1]-C[1]) - R) > 0.2:
			# Geometric failure tolerance -> skip
			return
		# Clear existing planView children
		for child in list(plan_elem):
			plan_elem.remove(child)
		# Emit line from p_in to T_in
		S0 = 0.0
		L1 = max(0.0, math.hypot(T_in[0]-p_in[0], T_in[1]-p_in[1]))
		if L1 > 1e-3:
			geom1 = ET.SubElement(plan_elem, "geometry", s=f"{S0:.3f}", x=f"{p_in[0]:.3f}", y=f"{p_in[1]:.3f}", hdg=f"{h_in:.6f}", length=f"{L1:.3f}")
			ET.SubElement(geom1, "line")
		# Emit arc from T_in to T_out
		S1 = S0 + L1
		ang_arc = abs(self._normalize_angle(math.atan2(T_out[1]-C[1], T_out[0]-C[0]) - math.atan2(T_in[1]-C[1], T_in[0]-C[0])))
		Larc = R * ang_arc
		if Larc > 1e-3:
			geom2 = ET.SubElement(plan_elem, "geometry", s=f"{S1:.3f}", x=f"{T_in[0]:.3f}", y=f"{T_in[1]:.3f}", hdg=f"{math.atan2(T_in[1]-C[1], T_in[0]-C[0]) + (math.pi/2.0 * sign):.6f}", length=f"{Larc:.3f}")
			ET.SubElement(geom2, "arc", curvature=f"{sign / R:.12f}")
		# Emit line from T_out to p_out
		S2 = S1 + Larc
		L3 = max(0.0, math.hypot(p_out[0]-T_out[0], p_out[1]-T_out[1]))
		if L3 > 1e-3:
			geom3 = ET.SubElement(plan_elem, "geometry", s=f"{S2:.3f}", x=f"{T_out[0]:.3f}", y=f"{T_out[1]:.3f}", hdg=f"{h_out:.6f}", length=f"{L3:.3f}")
			ET.SubElement(geom3, "line")

	@staticmethod
	def _fit_cubic_least_squares(p: List[float], y: List[float]) -> Tuple[float,float,float,float]:
		"""Fit y ~ a + b*p + c*p^2 + d*p^3 in least squares sense."""
		n = len(p)
		if n != len(y) or n < 2:
			raise ValueError("Invalid data for cubic fit")
		# Build normal equations
		S = [0.0] * 7
		T = [0.0] * 4
		for i in range(n):
			pi = p[i]
			S[0] += 1.0
			S[1] += pi
			S[2] += pi**2
			S[3] += pi**3
			S[4] += pi**4
			S[5] += pi**5
			S[6] += pi**6
			T[0] += y[i]
			T[1] += y[i]*pi
			T[2] += y[i]*pi**2
			T[3] += y[i]*pi**3
		# Solve 4x4 system using Gaussian elimination
		A = [
			[S[0], S[1], S[2], S[3]],
			[S[1], S[2], S[3], S[4]],
			[S[2], S[3], S[4], S[5]],
			[S[3], S[4], S[5], S[6]],
		]
		b = [T[0], T[1], T[2], T[3]]
		# Forward elimination
		for i in range(4):
			# Pivot
			pivot = A[i][i]
			if abs(pivot) < 1e-12:
				raise ValueError("Singular matrix in cubic fit")
			inv_p = 1.0 / pivot
			for j in range(i, 4):
				A[i][j] *= inv_p
			b[i] *= inv_p
			# Eliminate
			for k in range(i+1, 4):
				factor = A[k][i]
				for j in range(i, 4):
					A[k][j] -= factor * A[i][j]
				b[k] -= factor * b[i]
		# Back substitution
		for i in range(3, -1, -1):
			for k in range(i-1, -1, -1):
				factor = A[k][i]
				A[k][i] -= factor * A[i][i]
				b[k] -= factor * b[i]
		return b[0], b[1], b[2], b[3]