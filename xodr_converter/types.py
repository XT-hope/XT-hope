from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class GPSRecord:
	# Timestamp in seconds (float)
	ts: float
	lat: float
	lon: float
	heading_deg: float
	speed_mps: Optional[float] = None


@dataclass
class LaneLine:
	id: str
	# Polyline points in ego frame (x forward, y left), meters
	points_xy: List[Tuple[float, float]]


@dataclass
class ZebraCrossing:
	# Polygon outline in ego frame (x, y) meters or centerline; we use polygon
	polygon_xy: List[Tuple[float, float]]


@dataclass
class BEVFrame:
	ts: float
	lane_lines: List[LaneLine] = field(default_factory=list)
	zebras: List[ZebraCrossing] = field(default_factory=list)


@dataclass
class EgoPoseENU:
	# Ego pose in ENU at timestamp
	ts: float
	x_e: float
	y_n: float
	heading_deg: float