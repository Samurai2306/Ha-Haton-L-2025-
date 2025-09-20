import re
from typing import Optional, Tuple


def _parse_coord_pair(token: str) -> Optional[Tuple[float, float]]:
    """
    Parse compact lat/lon like 5957N02905E or 5957N030E.
    Returns (lat, lon) in decimal degrees or None if not matched.
    """
    if not token:
        return None

    # Pattern: DDMMNDDDMME or DDMMNDDDE
    m = re.fullmatch(r"(\d{2})(\d{2})([NS])(\d{3})(\d{2})([EW])", token)
    if m:
        dlat, mlat, ns, dlon, mlon, ew = m.groups()
        lat = int(dlat) + int(mlat) / 60.0
        lon = int(dlon) + int(mlon) / 60.0
        if ns == "S":
            lat = -lat
        if ew == "W":
            lon = -lon
        return (lat, lon)

    # Pattern: DDMMNDDDE or DDNDDDE (fallbacks)
    m2 = re.fullmatch(r"(\d{2})(\d{2})([NS])(\d{3})([EW])", token)
    if m2:
        dlat, mlat, ns, dlon, ew = m2.groups()
        lat = int(dlat) + int(mlat) / 60.0
        lon = float(int(dlon))
        if ns == "S":
            lat = -lat
        if ew == "W":
            lon = -lon
        return (lat, lon)

    m3 = re.fullmatch(r"(\d{2})([NS])(\d{3})([EW])", token)
    if m3:
        dlat, ns, dlon, ew = m3.groups()
        lat = float(int(dlat))
        lon = float(int(dlon))
        if ns == "S":
            lat = -lat
        if ew == "W":
            lon = -lon
        return (lat, lon)

    return None


def try_parse_coord(token: str) -> Tuple[float | None, float | None]:
    pair = _parse_coord_pair(token) if token else None
    if pair is None:
        return (None, None)
    return pair

