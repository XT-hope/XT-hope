from dataclasses import dataclass
from typing import Tuple
import math


@dataclass
class ReferenceOrigin:
    lat0: float
    lon0: float
    alt0: float = 0.0


class CoordinateConverter:
    """Converts GPS WGS84 (lat, lon, heading) to local ENU and transforms ego-frame points to ENU.
    Uses a local tangent plane approximation suitable for short trajectories.
    """

    def __init__(self, ref: ReferenceOrigin) -> None:
        self._ref = ref
        self._lat0_rad = math.radians(ref.lat0)
        # WGS84 mean Earth radius (approx.) in meters
        self._R = 6378137.0

    def wgs84_to_enu(self, lon: float, lat: float) -> Tuple[float, float]:
        dlat = math.radians(lat - self._ref.lat0)
        dlon = math.radians(lon - self._ref.lon0)
        x_e = dlon * math.cos(self._lat0_rad) * self._R
        y_n = dlat * self._R
        return float(x_e), float(y_n)

    @staticmethod
    def ego_to_enu(x_ego: float, y_ego: float, enu_x: float, enu_y: float, heading_deg: float) -> Tuple[float, float]:
        """Transform ego-centric point (x forward, y left) into ENU world given ego pose.
        heading_deg is vehicle yaw clockwise from North.
        """
        yaw_from_east_ccw = math.radians(90.0 - heading_deg)
        cos_yaw = math.cos(yaw_from_east_ccw)
        sin_yaw = math.sin(yaw_from_east_ccw)
        x_world = cos_yaw * x_ego - sin_yaw * y_ego
        y_world = sin_yaw * x_ego + cos_yaw * y_ego
        return enu_x + x_world, enu_y + y_world

    @staticmethod
    def normalize_angle_deg(angle_deg: float) -> float:
        a = (angle_deg + 180.0) % 360.0 - 180.0
        return a