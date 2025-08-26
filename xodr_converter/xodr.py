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
		self._emit_plan_view(plan, trajectory_xy)
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

	@staticmethod
	def _heading(x0: float, y0: float, x1: float, y1: float) -> float:
		return math.atan2(y1 - y0, x1 - x0)