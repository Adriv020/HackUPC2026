"""
csv_to_world.py
~~~~~~~~~~~~~~~
Converts the raw Mecalux CSV inputs + solver output CSV into a
WorldResponse-shaped dict that the WarehouseOS Next.js front-end
(lib/world-mapper.ts) already knows how to render.

All input coordinates are in millimetres (mm).
"""

import os
import math


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def _numeric_rows(path):
    """Yield rows from a CSV file where the first token is numeric."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = [p.strip() for p in line.split(",")]
            if not parts or not parts[0]:
                continue
            try:
                float(parts[0])
                yield parts
            except ValueError:
                pass  # skip header / blank rows


def parse_warehouse(path):
    """Returns list of {"x": float, "y": float} perimeter points in mm."""
    points = []
    for parts in _numeric_rows(path):
        if len(parts) >= 2:
            try:
                points.append({"x": float(parts[0]), "y": float(parts[1])})
            except ValueError:
                pass
    return points


def parse_obstacles(path):
    """Returns list of obstacle dicts (x, y = BL corner, width, depth, height)."""
    obstacles = []
    if not path or not os.path.exists(path):
        return obstacles
    for parts in _numeric_rows(path):
        if len(parts) >= 4:
            try:
                obstacles.append({
                    "x":      float(parts[0]),
                    "y":      float(parts[1]),
                    "width":  float(parts[2]),
                    "depth":  float(parts[3]),
                    "height": float(parts[4]) if len(parts) >= 5 else 3000,
                })
            except ValueError:
                pass
    return obstacles


def parse_ceiling(path):
    """
    Returns list of {"xFrom", "xTo", "maxHeight"} segments.
    Input rows: coordX, ceilingHeight — sorted ascending by X.
    Consecutive rows form piecewise segments; the last segment extends to xTo = xFrom+1.
    """
    rows = []
    for parts in _numeric_rows(path):
        if len(parts) >= 2:
            try:
                rows.append((float(parts[0]), float(parts[1])))
            except ValueError:
                pass
    rows.sort(key=lambda r: r[0])

    segments = []
    for i, (x, h) in enumerate(rows):
        x_to = rows[i + 1][0] if i + 1 < len(rows) else x + 1.0
        segments.append({"xFrom": x, "xTo": x_to, "maxHeight": h})
    return segments


def parse_bay_types(path):
    """
    Returns dict: str(type_id) → {width, depth, height, nLoads, price}
    CSV columns: type_id, width_mm, depth_mm, height_mm, gap_mm, nLoads, price
    """
    types = {}
    if not os.path.exists(path):
        return types
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 7:
                continue
            type_id = parts[0]
            # Skip header rows
            if type_id.lower() in ("type_id", "id", "typeid"):
                continue
            try:
                width  = float(parts[1])
                depth  = float(parts[2])
                height = float(parts[3])
                # parts[4] = gap, parts[5] = nLoads, parts[6] = price
                n_loads = int(float(parts[5]))
                price   = float(parts[6]) if parts[6] else 0.0
                types[type_id] = {
                    "width":  width,
                    "depth":  depth,
                    "height": height,
                    "nLoads": n_loads,
                    "price":  price,
                }
            except (ValueError, IndexError):
                pass
    return types


def parse_solution(path, bay_types):
    """
    Parse output_caseN.csv (Id, X, Y, Rotation) into a list of bay dicts
    that match the WorldResponse.rows[].bays[] schema.

    (X, Y) is the origin corner of the OBB (same convention as validator's
    get_obb_corners).  Width runs along (cos θ, sin θ) and depth along
    (-sin θ, cos θ), so the geometric centre is:
      cx = X + (w/2)·cos θ − (d/2)·sin θ
      cy = Y + (w/2)·sin θ + (d/2)·cos θ
    This is exact for any rotation angle, not just multiples of 90°.
    """
    bays = []
    bay_idx = 0

    if not os.path.exists(path):
        return bays

    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 4:
                continue
            type_id_raw = parts[0]
            if type_id_raw.lower() in ("id", "type_id"):
                continue  # header row
            try:
                x        = float(parts[1])
                y        = float(parts[2])
                rotation = float(parts[3])
            except ValueError:
                continue

            # Normalise type_id to string key used in bay_types dict
            type_key = type_id_raw
            if type_key not in bay_types:
                # try integer string, e.g. "2.0" → "2"
                try:
                    type_key = str(int(float(type_id_raw)))
                except ValueError:
                    pass

            bt = bay_types.get(type_key)
            if bt is None:
                continue  # unknown bay type — skip

            w, d = bt["width"], bt["depth"]

            # BL-corner → geometric centre for any rotation angle.
            # The validator/solver use get_obb_corners(x,y,w,d,θ):
            #   width direction = (cos θ,  sin θ)
            #   depth direction = (-sin θ, cos θ)
            # So centre = corner + (w/2)·width_dir + (d/2)·depth_dir
            rad = math.radians(rotation)
            cos_a = math.cos(rad)
            sin_a = math.sin(rad)
            cx = x + (w / 2.0) * cos_a - (d / 2.0) * sin_a
            cy = y + (w / 2.0) * sin_a + (d / 2.0) * cos_a

            bays.append({
                "bayId":    f"bay-{bay_idx}",
                "typeId":   int(float(type_id_raw)),
                "position": {"x": cx, "y": cy, "z": 0},
                "rotation": rotation,
                "dimensions": {
                    "width":  w,
                    "depth":  d,
                    "height": bt["height"],
                },
                "nLoads": bt["nLoads"],
                "price":  bt["price"],
            })
            bay_idx += 1

    return bays


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_world_response(p_warehouse, p_obstacles, p_ceiling, p_bay_types, p_solution):
    """
    Build and return a WorldResponse-shaped dict from the five CSV file paths.
    Safe to call even if obstacles.csv is missing (returns empty list).
    """
    perimeter  = parse_warehouse(p_warehouse)
    obstacles  = parse_obstacles(p_obstacles)
    ceiling    = parse_ceiling(p_ceiling)
    bay_types  = parse_bay_types(p_bay_types)
    bays       = parse_solution(p_solution, bay_types)

    xs = [p["x"] for p in perimeter] or [0]
    ys = [p["y"] for p in perimeter] or [0]

    total_revenue = sum(b["price"] for b in bays)

    return {
        "warehouse": {
            "perimeter": perimeter,
            "boundingBox": {
                "minX": min(xs), "minY": min(ys),
                "maxX": max(xs), "maxY": max(ys),
            },
            "unit": "mm",
        },
        "obstacles": obstacles,
        "ceiling":   ceiling,
        "rows": [{"rowId": "r0", "bays": bays}],
        "summary": {
            "totalBays":     len(bays),
            "totalRevenue":  total_revenue,
        },
    }
