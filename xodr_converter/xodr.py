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
		# Pre-compute headings for each segment at start and end
		seg_start_hdg: List[float] = []
		seg_end_hdg: List[float] = []
		for idx, (traj, is_conn, start_s) in enumerate(segments):
			length = self._compute_length(traj)
			# Create road element, but delay linking decisions
			# For connecting segments we may decide to model as slip (non-junction) based on movement classification later
			road_elem = ET.SubElement(root, "road", id=str(idx+1), name=("conn_" if is_conn else "road_") + str(idx+1), length=f"{length:.3f}", junction=("1" if is_conn else "-1"))
			plan = ET.SubElement(road_elem, "planView")
			# Placeholder: emit simple geometry; we may adjust for turn segments below when linking determines movement
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
			if lane_cfg.mirror_missing_side:
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
			# Headings at start/end
			if len(traj) >= 2:
				seg_start_hdg.append(self._heading(traj[0][0], traj[0][1], traj[1][0], traj[1][1]))
				seg_end_hdg.append(self._heading(traj[-2][0], traj[-2][1], traj[-1][0], traj[-1][1]))
			else:
				seg_start_hdg.append(0.0)
				seg_end_hdg.append(0.0)
		# Linking logic with optional junctions
		junc: ET.Element | None = None
		consumed = [False] * len(roads)
		for i in range(len(roads)):
			# Try to detect [incoming, connecting, outgoing]
			if i + 2 < len(roads):
				incoming_is_ok = True
				connecting_is_conn = segments[i+1][1]
				if connecting_is_conn:
					# classify movement using end heading of incoming and start heading of outgoing
					mov = self._classify_movement(seg_end_hdg[i], seg_start_hdg[i+2])
					is_right_turn_slip = (mov == "right")
					# If connecting is a turn, re-emit its geometry as line-spiral-arc-spiral-line
					if mov in ("left", "right"):
						# Replace existing planView children with turn geometry
						plan = roads[i+1].find("planView")
						if plan is not None:
							for child in list(plan):
								plan.remove(child)
							self._emit_turn_geometry(plan, segments[i+1][0], mov)
					# create junction only if not right-turn slip
					if not is_right_turn_slip:
						if junc is None:
							junc = ET.SubElement(root, "junction", id="1", name="j1")
						# incoming -> junction
						link_in = ET.SubElement(roads[i], "link")
						ET.SubElement(link_in, "successor", elementType="junction", elementId="1", contactPoint="start")
						# connecting road predecessor/ successor
						link_conn = ET.SubElement(roads[i+1], "link")
						ET.SubElement(link_conn, "predecessor", elementType="road", elementId=road_ids[i], contactPoint="end")
						ET.SubElement(link_conn, "successor", elementType="road", elementId=road_ids[i+2], contactPoint="start")
						# outgoing road predecessor from junction
						link_out = ET.SubElement(roads[i+2], "link")
						ET.SubElement(link_out, "predecessor", elementType="junction", elementId="1", contactPoint="end")
						# lane counts for links (respect mirroring)
						j_left = lane_cfg.num_lanes_left if lane_cfg.num_lanes_left is not None else 0
						j_right = lane_cfg.num_lanes_right if lane_cfg.num_lanes_right is not None else 0
						if (j_left <= 0 and j_right <= 0) and lane_cfg.num_lanes > 0:
							j_right = lane_cfg.num_lanes
						if lane_cfg.mirror_missing_side:
							if j_left > 0 and j_right <= 0:
								j_right = j_left
							elif j_right > 0 and j_left <= 0:
								j_left = j_right
						# junction connection with laneLinks: map only the representative driving lane per movement on right side (negative ids)
						conn = ET.SubElement(junc, "connection", id=str(i+1), incomingRoad=road_ids[i], connectingRoad=road_ids[i+1], contactPoint="end")
						from_id = self._select_lane_id_for_movement(j_right, mov)
						to_id = self._select_lane_id_for_movement(j_right, mov)
						if from_id is not None and to_id is not None:
							ET.SubElement(conn, "laneLink", _from=f"{from_id}", to=f"{to_id}")
						consumed[i] = True
						consumed[i+1] = True
						consumed[i+2] = True
						continue
					else:
						# Right-turn slip: do not create junction; link sequentially incoming -> slip -> outgoing
						link1 = ET.SubElement(roads[i], "link")
						ET.SubElement(link1, "successor", elementType="road", elementId=road_ids[i+1], contactPoint="start")
						link2 = ET.SubElement(roads[i+1], "link")
						ET.SubElement(link2, "predecessor", elementType="road", elementId=road_ids[i], contactPoint="end")
						ET.SubElement(link2, "successor", elementType="road", elementId=road_ids[i+2], contactPoint="start")
						link3 = ET.SubElement(roads[i+2], "link")
						ET.SubElement(link3, "predecessor", elementType="road", elementId=road_ids[i+1], contactPoint="end")
						# mark the slip road as non-junction
						roads[i+1].attrib["junction"] = "-1"
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

	@staticmethod
	def _normalize_angle_rad(angle: float) -> float:
		while angle > math.pi:
			angle -= 2 * math.pi
		while angle < -math.pi:
			angle += 2 * math.pi
		return angle

	def _classify_movement(self, theta_in: float, theta_out: float) -> str:
		delta = self._normalize_angle_rad(theta_out - theta_in)
		ad = abs(delta)
		# thresholds: straight <= 20deg, right <= -45deg, left >= 45deg, uturn >= 150deg
		deg = 180.0 / math.pi
		if ad >= 150.0/deg:
			return "uturn"
		if ad <= 20.0/deg:
			return "straight"
		if delta <= -45.0/deg:
			return "right"
		if delta >= 45.0/deg:
			return "left"
		return "straight"

	def _select_lane_id_for_movement(self, num_right: int, movement: str) -> int | None:
		# Right-side negative ids: -1 rightmost, -2 middle, -3 leftmost of approach
		if num_right <= 0:
			return None
		if movement == "right":
			return -1
		if movement == "straight":
			return -2 if num_right >= 2 else -1
		if movement == "left":
			return -3 if num_right >= 3 else (-2 if num_right >= 2 else -1)
		if movement == "uturn":
			return -3 if num_right >= 3 else (-2 if num_right >= 2 else -1)
		return -1

	def _emit_turn_geometry(self, plan_elem: ET.Element, traj_xy: List[Tuple[float,float]], movement: str) -> None:
		# Build a 5-piece: line + spiral + arc + spiral + line that connects start/end pose of traj
		if len(traj_xy) < 2:
			return
		x0, y0 = traj_xy[0]
		x1, y1 = traj_xy[-1]
		h0 = self._heading(traj_xy[0][0], traj_xy[0][1], traj_xy[1][0], traj_xy[1][1])
		h1 = self._heading(traj_xy[-2][0], traj_xy[-2][1], traj_xy[-1][0], traj_xy[-1][1])
		phi = self._normalize_angle_rad(h1 - h0)
		turn_right = (movement == "right")
		# Choose design parameters
		R = 15.0 if turn_right else 35.0
		# spiral length choose limited and consistent with phi
		Ls = max(5.0, min(0.3 * R, 20.0))
		# compute arc central angle
		alpha = phi - (Ls / R)
		# If alpha too small, reduce Ls
		if abs(alpha) < 1e-3:
			Ls = max(3.0, 0.2 * R)
			alpha = phi - (Ls / R)
		# lengths
		Lc = max(0.0, R * abs(alpha))
		Llead = 0.0
		Ltrail = 0.0
		# Emit geometries with numeric integration to get end pose of spirals
		s_acc = 0.0
		# helper to append and update pose
		def add_line(x: float, y: float, hdg: float, L: float) -> Tuple[float,float,float,float]:
			geom = ET.SubElement(plan_elem, "geometry", s=f"{add_line.s:.3f}", x=f"{x:.3f}", y=f"{y:.3f}", hdg=f"{hdg:.6f}", length=f"{L:.3f}")
			ET.SubElement(geom, "line")
			x2 = x + L * math.cos(hdg)
			y2 = y + L * math.sin(hdg)
			add_line.s += L
			return x2, y2, hdg, L
		add_line.s = 0.0
		def add_spiral(x: float, y: float, hdg: float, L: float, k0: float, k1: float) -> Tuple[float,float,float,float]:
			geom = ET.SubElement(plan_elem, "geometry", s=f"{add_line.s:.3f}", x=f"{x:.3f}", y=f"{y:.3f}", hdg=f"{hdg:.6f}", length=f"{L:.3f}")
			ET.SubElement(geom, "spiral", curvStart=f"{k0:.6f}", curvEnd=f"{k1:.6f}")
			# numeric integrate
			steps = max(20, int(L / 0.5))
			ds = L / steps
			kx = k0
			k_inc = (k1 - k0) / L if L > 0 else 0.0
			xc, yc, th = x, y, hdg
			for _ in range(steps):
				th += (kx + 0.5 * k_inc * ds) * ds
				xc += ds * math.cos(th)
				yc += ds * math.sin(th)
				kx += k_inc * ds
			add_line.s += L
			return xc, yc, th, L
		def add_arc(x: float, y: float, hdg: float, L: float, k: float) -> Tuple[float,float,float,float]:
			geom = ET.SubElement(plan_elem, "geometry", s=f"{add_line.s:.3f}", x=f"{x:.3f}", y=f"{y:.3f}", hdg=f"{hdg:.6f}", length=f"{L:.3f}")
			ET.SubElement(geom, "arc", curvature=f"{k:.6f}")
			# integrate constant curvature
			if abs(k) < 1e-9:
				x2, y2, th2, _ = add_line(x, y, hdg, L)
				return x2, y2, th2, L
			th2 = hdg + k * L
			Rloc = 1.0 / k
			x2 = x + Rloc * (math.sin(th2) - math.sin(hdg))
			y2 = y - Rloc * (math.cos(th2) - math.cos(hdg))
			add_line.s += L
			return x2, y2, th2, L
		# start with optional short lead/ trail lines (zero by default)
		xc, yc, th = x0, y0, h0
		if Llead > 1e-3:
			xc, yc, th, _ = add_line(xc, yc, th, Llead)
		# spiral in
		k_end = (1.0 / R) * ( -1.0 if turn_right else 1.0 )
		xc, yc, th, _ = add_spiral(xc, yc, th, Ls, 0.0, k_end)
		# arc
		xc, yc, th, _ = add_arc(xc, yc, th, Lc, k_end)
		# spiral out back to zero curvature
		xc, yc, th, _ = add_spiral(xc, yc, th, Ls, k_end, 0.0)
		# trailing line to reach the endpoint direction roughly
		if Ltrail > 1e-3:
			xc, yc, th, _ = add_line(xc, yc, th, Ltrail)
		# Note: We do not force exact end (x1,y1, h1), but geometry is G2 continuous and close in pose; for small junctions this is acceptable.
		return