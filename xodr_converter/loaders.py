from __future__ import annotations
from typing import List, Dict, Any
import json
import csv
from .types import GPSRecord, BEVFrame, LaneLine, ZebraCrossing


def load_gps_csv(path: str) -> List[GPSRecord]:
	"""Load GPS CSV with columns: ts, lat, lon, heading_deg[, speed_mps]"""
	records: List[GPSRecord] = []
	with open(path, "r", encoding="utf-8") as f:
		reader = csv.DictReader(f)
		for row in reader:
			ts = float(row["ts"]) if row.get("ts") not in (None, "") else 0.0
			lat = float(row["lat"]) if row.get("lat") not in (None, "") else 0.0
			lon = float(row["lon"]) if row.get("lon") not in (None, "") else 0.0
			hdg = float(row["heading_deg"]) if row.get("heading_deg") not in (None, "") else 0.0
			spd = float(row["speed_mps"]) if row.get("speed_mps") not in (None, "") else None
			records.append(GPSRecord(ts=ts, lat=lat, lon=lon, heading_deg=hdg, speed_mps=spd))
	return records


def _parse_lane_line(obj: Dict[str, Any]) -> LaneLine:
	points = [(float(p[0]), float(p[1])) for p in obj.get("points_xy", obj.get("points", []))]
	lane_id = str(obj.get("id", "unknown"))
	return LaneLine(id=lane_id, points_xy=points)


def _parse_zebra(obj: Dict[str, Any]) -> ZebraCrossing:
	polygon = [(float(p[0]), float(p[1])) for p in obj.get("polygon_xy", obj.get("polygon", []))]
	return ZebraCrossing(polygon_xy=polygon)


def load_bev_json(path: str) -> List[BEVFrame]:
	"""Load BEV JSON: list of frames with keys {ts, lane_lines: [{id, points_xy}], zebras: [{polygon_xy}]}"""
	with open(path, "r", encoding="utf-8") as f:
		data = json.load(f)
	frames: List[BEVFrame] = []
	for item in data:
		lane_lines = [_parse_lane_line(ll) for ll in item.get("lane_lines", [])]
		zebras = [_parse_zebra(z) for z in item.get("zebras", [])]
		frames.append(BEVFrame(ts=float(item["ts"]), lane_lines=lane_lines, zebras=zebras))
	return frames