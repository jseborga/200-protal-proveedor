"""Open Location Code (Plus Code) decoder.

Minimal self-contained implementation based on the public Google spec
(https://github.com/google/open-location-code). Supports:
  - Full codes (e.g. "8FVC2222+22"): decoded directly
  - Short codes (e.g. "FR9H+25W"): need a reference lat/lng to recover

No external dependencies.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

CODE_ALPHABET = "23456789CFGHJMPQRVWX"
ENCODING_BASE = len(CODE_ALPHABET)
SEPARATOR = "+"
SEPARATOR_POSITION = 8
PADDING_CHAR = "0"
PAIR_CODE_LENGTH = 10
GRID_CODE_LENGTH = 5
GRID_COLUMNS = 4
GRID_ROWS = 5
LATITUDE_MAX = 90
LONGITUDE_MAX = 180

# Matches any Plus Code fragment (full or short) within a larger string.
PLUSCODE_RE = re.compile(
    r"([" + CODE_ALPHABET + r"]{2,8})\+([" + CODE_ALPHABET + r"0]{0,3})",
    re.IGNORECASE,
)


@dataclass
class CodeArea:
    lat_lo: float
    lon_lo: float
    lat_hi: float
    lon_hi: float

    @property
    def lat_center(self) -> float:
        return min(LATITUDE_MAX, max(-LATITUDE_MAX, (self.lat_lo + self.lat_hi) / 2))

    @property
    def lon_center(self) -> float:
        return (self.lon_lo + self.lon_hi) / 2


def _clean(code: str) -> str:
    return code.replace(" ", "").upper()


def is_valid(code: str) -> bool:
    if not code:
        return False
    code = _clean(code)
    if SEPARATOR not in code or code.count(SEPARATOR) != 1:
        return False
    sep = code.index(SEPARATOR)
    if sep > SEPARATOR_POSITION or sep % 2 == 1:
        return False
    if PADDING_CHAR in code:
        if sep < SEPARATOR_POSITION:
            return False
        if code.index(PADDING_CHAR) % 2 == 1:
            return False
        stripped = code.rstrip(PADDING_CHAR + SEPARATOR)
        if PADDING_CHAR in stripped:
            return False
    if len(code) - sep - 1 == 1:
        return False
    for ch in code.replace(SEPARATOR, "").replace(PADDING_CHAR, ""):
        if ch not in CODE_ALPHABET:
            return False
    return True


def is_full(code: str) -> bool:
    if not is_valid(code):
        return False
    code = _clean(code)
    # First character encodes 20 deg of latitude (0..17 valid)
    first_lat = CODE_ALPHABET.index(code[0]) * ENCODING_BASE
    if first_lat >= LATITUDE_MAX * 2:
        return False
    if len(code) >= 2:
        first_lon = CODE_ALPHABET.index(code[1]) * ENCODING_BASE
        if first_lon >= LONGITUDE_MAX * 2:
            return False
    return True


def is_short(code: str) -> bool:
    if not is_valid(code):
        return False
    return not is_full(code)


def decode(code: str) -> CodeArea:
    """Decode a full Plus Code to a CodeArea. Raises on invalid/short code."""
    if not is_full(code):
        raise ValueError(f"Not a full Plus Code: {code}")
    code = _clean(code).replace(SEPARATOR, "")
    # Strip padding
    code = code.replace(PADDING_CHAR, "")

    lat = -LATITUDE_MAX
    lon = -LONGITUDE_MAX
    lat_res = ENCODING_BASE ** 2
    lon_res = ENCODING_BASE ** 2

    # First 10 chars = pairs (lat, lon), each pair narrows by ENCODING_BASE
    digits = code[:PAIR_CODE_LENGTH]
    for i in range(0, len(digits), 2):
        lat_res /= ENCODING_BASE
        lon_res /= ENCODING_BASE
        lat += CODE_ALPHABET.index(digits[i]) * lat_res
        lon += CODE_ALPHABET.index(digits[i + 1]) * lon_res

    if len(code) <= PAIR_CODE_LENGTH:
        return CodeArea(lat, lon, lat + lat_res, lon + lon_res)

    # Remaining chars = grid refinement (base 20, rows=5, cols=4)
    grid_lat_res = lat_res
    grid_lon_res = lon_res
    for ch in code[PAIR_CODE_LENGTH : PAIR_CODE_LENGTH + GRID_CODE_LENGTH]:
        grid_lat_res /= GRID_ROWS
        grid_lon_res /= GRID_COLUMNS
        idx = CODE_ALPHABET.index(ch)
        row = idx // GRID_COLUMNS
        col = idx % GRID_COLUMNS
        lat += row * grid_lat_res
        lon += col * grid_lon_res

    return CodeArea(lat, lon, lat + grid_lat_res, lon + grid_lon_res)


def recover_nearest(short_code: str, ref_lat: float, ref_lon: float) -> str:
    """Recover a full Plus Code from a short code near a reference point."""
    if not is_short(short_code):
        if is_full(short_code):
            return _clean(short_code)
        raise ValueError(f"Not a valid short Plus Code: {short_code}")

    short = _clean(short_code)
    # Clamp reference
    ref_lat = min(LATITUDE_MAX - 1e-10, max(-LATITUDE_MAX, ref_lat))
    ref_lon = ((ref_lon + 180) % 360 + 360) % 360 - 180

    padding_len = SEPARATOR_POSITION - short.index(SEPARATOR)
    # Resolution of the missing prefix
    resolution = ENCODING_BASE ** (2 - (padding_len // 2))
    half = resolution / 2

    # Build code prefix from reference point rounded down to resolution
    prefix_lat = (ref_lat + LATITUDE_MAX) // resolution * resolution - LATITUDE_MAX
    prefix_lon = (ref_lon + LONGITUDE_MAX) // resolution * resolution - LONGITUDE_MAX

    # Encode that prefix
    prefix_code = _encode_prefix(prefix_lat, prefix_lon, padding_len)
    candidate = prefix_code + short
    area = decode(candidate)

    # Move by resolution toward ref if center is farther than half-resolution
    center_lat = area.lat_center
    center_lon = area.lon_center
    if ref_lat + half < center_lat and area.lat_lo - resolution >= -LATITUDE_MAX:
        prefix_lat -= resolution
    elif ref_lat - half > center_lat and area.lat_lo + resolution < LATITUDE_MAX:
        prefix_lat += resolution
    if ref_lon + half < center_lon:
        prefix_lon -= resolution
    elif ref_lon - half > center_lon:
        prefix_lon += resolution

    prefix_code = _encode_prefix(prefix_lat, prefix_lon, padding_len)
    return prefix_code + short


def _encode_prefix(lat: float, lon: float, padding_len: int) -> str:
    """Encode the first `padding_len` characters of a code from lat/lon."""
    lat += LATITUDE_MAX
    lon += LONGITUDE_MAX
    code = ""
    lat_val = int(lat * (ENCODING_BASE ** 2) / 1) * 1  # integer work not needed; keep as float
    # Reproduce encoder for pair section up to padding_len chars
    # We emit pairs: first pair is (deg / 20), second is (deg / 1), etc.
    divisors_lat = [20.0, 1.0, 0.05, 0.0025, 0.000125]
    divisors_lon = [20.0, 1.0, 0.05, 0.0025, 0.000125]
    pair_idx = 0
    while len(code) < padding_len and pair_idx < len(divisors_lat):
        dlat = divisors_lat[pair_idx]
        dlon = divisors_lon[pair_idx]
        ilat = int(lat // dlat)
        ilon = int(lon // dlon)
        # Clamp into alphabet range
        ilat = max(0, min(ENCODING_BASE - 1, ilat))
        ilon = max(0, min(ENCODING_BASE - 1, ilon))
        code += CODE_ALPHABET[ilat] + CODE_ALPHABET[ilon]
        lat -= ilat * dlat
        lon -= ilon * dlon
        pair_idx += 1
    return code[:padding_len]


def extract(text: str) -> str | None:
    """Return the first Plus Code fragment found in `text`, or None."""
    if not text:
        return None
    m = PLUSCODE_RE.search(text)
    if not m:
        return None
    code = (m.group(1) + SEPARATOR + m.group(2)).upper()
    # Trim trailing dots/commas etc already handled by regex
    if is_valid(code):
        return code
    return None


def decode_to_latlng(
    code: str,
    ref_lat: float | None = None,
    ref_lon: float | None = None,
) -> tuple[float, float] | None:
    """Decode a Plus Code (full or short) to (lat, lon). Returns None on failure."""
    try:
        code = _clean(code)
        if is_full(code):
            area = decode(code)
            return (area.lat_center, area.lon_center)
        if is_short(code):
            if ref_lat is None or ref_lon is None:
                return None
            full = recover_nearest(code, ref_lat, ref_lon)
            area = decode(full)
            return (area.lat_center, area.lon_center)
    except Exception:
        return None
    return None
