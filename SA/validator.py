#!/usr/bin/env python3
"""
Validator for the Mecalux Warehouse Bay Placement challenge (HackUPC 2026).

Checks all constraints and computes the quality score Q if valid.

Usage:
    python validator.py <warehouse.csv> <obstacles.csv> <ceiling.csv> <bays.csv> <solution.csv>

Exit code 0 = valid, 1 = invalid.
"""

import sys
import math

EPS = 1e-9

def get_obb_corners(x_bl, y_bl, w, h, angle_deg):
    rad = math.radians(angle_deg)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)
    return (
        (x_bl, y_bl),
        (x_bl + w * cos_a, y_bl + w * sin_a),
        (x_bl + w * cos_a - h * sin_a, y_bl + w * sin_a + h * cos_a),
        (x_bl - h * sin_a, y_bl + h * cos_a)
    )

def aabb_from_corners(c):
    xs = [p[0] for p in c]
    ys = [p[1] for p in c]
    return min(xs), min(ys), max(xs), max(ys)

def sat_overlap(c1, c2):
    for poly in (c1, c2):
        for i in range(len(poly)):
            p1 = poly[i]; p2 = poly[(i + 1) % 4]
            nx = p2[1] - p1[1]
            ny = p1[0] - p2[0]
            m1 = min(p[0]*nx + p[1]*ny for p in c1)
            M1 = max(p[0]*nx + p[1]*ny for p in c1)
            m2 = min(p[0]*nx + p[1]*ny for p in c2)
            M2 = max(p[0]*nx + p[1]*ny for p in c2)
            if M1 <= m2 + 1e-6 or M2 <= m1 + 1e-6:
                return False
    return True

def segments_intersect(p1, p2, p3, p4):
    def ccw(A, B, C):
        return (C[1]-A[1]) * (B[0]-A[0]) > (B[1]-A[1]) * (C[0]-A[0])
    return (ccw(p1, p3, p4) != ccw(p2, p3, p4)) and (ccw(p1, p2, p3) != ccw(p1, p2, p4))

def obb_inside(corners, verts):
    for cx, cy in corners:
        if not point_in_polygon(cx, cy, verts): return False, (cx, cy)
    for i in range(4):
        p1 = corners[i]; p2 = corners[(i+1)%4]
        n = len(verts)
        for j in range(n):
            w1 = verts[j]; w2 = verts[(j+1)%n]
            # Only flag intersection if neither point lies exactly on the wall segment
            if _point_on_segment(p1[0], p1[1], w1[0], w1[1], w2[0], w2[1]) or \
               _point_on_segment(p2[0], p2[1], w1[0], w1[1], w2[0], w2[1]):
                continue
            if segments_intersect(p1, p2, w1, w2): return False, p1
    return True, None

# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_csv_floats(path, min_cols):
    """Parse CSV, skip header/non-numeric rows, return list of float lists."""
    rows = []
    with open(path) as f:
        for ln in f:
            ln = ln.strip().replace('\r', '')
            if not ln:
                continue
            parts = ln.split(',')
            if len(parts) >= min_cols:
                try:
                    rows.append([float(x.strip()) for x in parts[:min_cols]])
                except ValueError:
                    continue
    return rows


def parse_warehouse(path):
    return parse_csv_floats(path, 2)


def parse_obstacles(path):
    return parse_csv_floats(path, 4)


def parse_ceiling(path):
    pts = parse_csv_floats(path, 2)
    pts.sort(key=lambda p: p[0])
    return pts


def parse_bay_types(path):
    rows = parse_csv_floats(path, 7)
    types = {}
    for r in rows:
        tid = int(r[0])
        types[tid] = {
            'id': tid,
            'width': r[1], 'depth': r[2],
            'height': r[3], 'gap': r[4],
            'nLoads': int(r[5]), 'price': r[6],
        }
    return types


def parse_solution(path):
    """Parse solution CSV. Returns list of dicts or error string."""
    bays = []
    with open(path) as f:
        lines = [ln.strip().replace('\r', '') for ln in f if ln.strip()]

    for i, ln in enumerate(lines):
        parts = ln.split(',')
        if len(parts) < 4:
            continue
        try:
            tid = int(parts[0].strip())
            x = float(parts[1].strip())
            y = float(parts[2].strip())
            rot = float(parts[3].strip())
            bays.append({'typeId': tid, 'x': x, 'y': y, 'rotation': rot, 'line': i + 1})
        except ValueError:
            # Skip header or malformed lines
            continue
    return bays


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

def polygon_area(verts):
    """Shoelace formula for polygon area."""
    n = len(verts)
    a = 0.0
    for i in range(n):
        j = (i + 1) % n
        a += verts[i][0] * verts[j][1] - verts[j][0] * verts[i][1]
    return abs(a) * 0.5


def point_in_polygon(px, py, verts):
    """
    Ray casting point-in-polygon. Returns True if point is inside or on boundary.
    Uses a horizontal ray to the right. Handles edge cases for axis-aligned polygons.
    """
    n = len(verts)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = verts[i]
        xj, yj = verts[j]

        # Check if point is exactly on this edge
        if _point_on_segment(px, py, xi, yi, xj, yj):
            return True

        if ((yi > py) != (yj > py)):
            x_intersect = xi + (py - yi) / (yj - yi) * (xj - xi)
            if px < x_intersect + EPS:
                inside = not inside
        j = i
    return inside


def _point_on_segment(px, py, x1, y1, x2, y2):
    """Check if (px,py) lies on segment (x1,y1)-(x2,y2) within tolerance."""
    # Cross product
    cross = (px - x1) * (y2 - y1) - (py - y1) * (x2 - x1)
    if abs(cross) > EPS * max(1, abs(x2 - x1), abs(y2 - y1)):
        return False
    # Check bounding box
    if px < min(x1, x2) - EPS or px > max(x1, x2) + EPS:
        return False
    if py < min(y1, y2) - EPS or py > max(y1, y2) + EPS:
        return False
    return True


def rect_in_polygon(x1, y1, x2, y2, verts):
    """Check all 4 corners of rectangle are inside polygon."""
    corners = [(x1, y1), (x2, y1), (x1, y2), (x2, y2)]
    for cx, cy in corners:
        if not point_in_polygon(cx, cy, verts):
            return False, (cx, cy)
    return True, None


def rects_overlap_strict(ax1, ay1, ax2, ay2, bx1, by1, bx2, by2):
    """Check if two rectangles have interior overlap (touching allowed)."""
    # Strict inequalities: overlap if interiors intersect
    return ax1 < bx2 - EPS and ax2 > bx1 + EPS and ay1 < by2 - EPS and ay2 > by1 + EPS


# ---------------------------------------------------------------------------
# Ceiling (step function)
# ---------------------------------------------------------------------------

def ceiling_at(ceil_pts, x):
    """Step function: each (x_i, h_i) means height is h_i from x_i onward."""
    if not ceil_pts:
        return 1e18
    if x < ceil_pts[0][0]:
        return ceil_pts[0][1]
    result = ceil_pts[0][1]
    for cx, ch in ceil_pts:
        if cx <= x:
            result = ch
        else:
            break
    return result


def min_ceiling(ceil_pts, x1, x2):
    """Minimum ceiling height over interval [x1, x2]."""
    h = ceiling_at(ceil_pts, x1)
    for cx, ch in ceil_pts:
        if cx > x2:
            break
        if cx > x1:
            h = min(h, ch)
    return h


# ---------------------------------------------------------------------------
# Bay footprint
# ---------------------------------------------------------------------------

def bay_footprint(bt, rotation):
    """Returns (w, d) after rotation, with gap added to the depth side (one end)."""
    w = bt['width']
    d = bt['depth'] + bt['gap']
    if rotation % 180 == 0:
        return w, d
    else:
        return d, w


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

def validate(wh_path, obs_path, ceil_path, bays_path, sol_path):
    errors = []

    print("VALIDATION REPORT")
    print("=================")
    print("Input files:")

    # Parse inputs
    wh_verts = parse_warehouse(wh_path)
    print(f"  warehouse.csv: OK ({len(wh_verts)} points)")

    obstacles = parse_obstacles(obs_path)
    print(f"  obstacles.csv: OK ({len(obstacles)} obstacles)")

    ceil_pts = parse_ceiling(ceil_path)
    print(f"  ceiling.csv:   OK ({len(ceil_pts)} points)")

    bay_types = parse_bay_types(bays_path)
    print(f"  bays.csv:      OK ({len(bay_types)} types)")

    placed = parse_solution(sol_path)
    print(f"  solution.csv:  OK ({len(placed)} bays placed)")

    print()
    print("Checking constraints...")

    # Precompute obstacle rects
    obs_rects = [(o[0], o[1], o[0] + o[2], o[1] + o[3]) for o in obstacles]

    # Compute bay footprints
    bay_rects = []  # (x1, y1, x2, y2, corners, bay_dict)
    wh_area = polygon_area(wh_verts)

    # --- Structural checks ---
    for i, b in enumerate(placed):
        rot = b['rotation']

        tid = b['typeId']
        if tid not in bay_types:
            errors.append(f"Bay #{i} (line {b['line']}): unknown type Id={tid}")
            continue

        bt = bay_types[tid]
        w = bt['width']
        d_full = bt['depth'] + bt['gap']
        d_bay = bt['depth']
        
        full_corners = get_obb_corners(b['x'], b['y'], w, d_full, rot)
        bay_corners = get_obb_corners(b['x'], b['y'], w, d_bay, rot)
        
        x1, y1, x2, y2 = aabb_from_corners(full_corners)
        bay_rects.append({
            'full_corners': full_corners,
            'bay_corners': bay_corners,
            'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2,
            'b': b, 'bt': bt, 'idx': i
        })

    # --- Constraint 1: Warehouse boundary ---
    wh_passes = 0
    for br in bay_rects:
        ok, corner = obb_inside(br['full_corners'], wh_verts)
        if not ok:
            errors.append(
                f"Bay #{br['idx']} (Id={br['b']['typeId']} at ({br['b']['x']:.1f}, {br['b']['y']:.1f}) rot {br['b']['rotation']}): "
                f"outside warehouse — corner ({corner[0]:.1f}, {corner[1]:.1f}) not inside polygon"
            )
        else:
            wh_passes += 1

    if wh_passes == len(bay_rects) and not any("outside warehouse" in e for e in errors):
        print("  All bays inside warehouse: PASS")
    else:
        print(f"  Warehouse boundary: FAIL ({len(bay_rects) - wh_passes} violations)")

    # --- Constraint 2: Obstacle avoidance ---
    obs_violations = 0
    for br in bay_rects:
        for oi, (ox1, oy1, ox2, oy2) in enumerate(obs_rects):
            obs_c = ((ox1, oy1), (ox2, oy1), (ox2, oy2), (ox1, oy2))
            if sat_overlap(br['full_corners'], obs_c):
                errors.append(
                    f"Bay #{br['idx']} (Id={br['b']['typeId']} at ({br['b']['x']:.1f}, {br['b']['y']:.1f}) rot {br['b']['rotation']}): "
                    f"overlaps obstacle {oi}"
                )
                obs_violations += 1

    if obs_violations == 0:
        print("  No bay overlaps obstacles: PASS")
    else:
        print(f"  Obstacle avoidance: FAIL ({obs_violations} violations)")

    # --- Constraint 3: Inter-bay non-overlap ---
    bay_violations = 0
    n = len(bay_rects)
    for i in range(n):
        bra = bay_rects[i]
        for j in range(i + 1, n):
            brb = bay_rects[j]
            # Gaps can overlap, but rack area cannot overlap any part of another bay
            if sat_overlap(bra['bay_corners'], brb['full_corners']) or \
               sat_overlap(brb['bay_corners'], bra['full_corners']):
                errors.append(
                    f"Bay #{bra['idx']} overlaps Bay #{brb['idx']} (non-gap areas)"
                )
                bay_violations += 1

    if bay_violations == 0:
        print("  No bays overlap each other: PASS")
    else:
        print(f"  Inter-bay non-overlap: FAIL ({bay_violations} violations)")

    # --- Constraint 4: Ceiling height ---
    ceil_violations = 0
    for br in bay_rects:
        min_h = min_ceiling(ceil_pts, br['x1'], br['x2'])
        req_h = br['bt']['height']
        if min_h < req_h - EPS:
            errors.append(
                f"Bay #{br['idx']} (Id={br['b']['typeId']} at ({br['b']['x']:.1f}, {br['b']['y']:.1f}) rot {br['b']['rotation']}): "
                f"ceiling too low — need {req_h:.0f}, have {min_h:.0f} "
                f"(x span [{br['x1']:.0f}, {br['x2']:.0f}])"
            )
            ceil_violations += 1

    if ceil_violations == 0:
        print("  Ceiling constraints satisfied: PASS")
    else:
        print(f"  Ceiling height: FAIL ({ceil_violations} violations)")

    # --- Report ---
    print()

    if errors:
        print("VIOLATIONS:")
        for e in errors:
            print(f"  ✗ {e}")
        print()
        print(f"STATUS: INVALID ({len(errors)} violation(s))")
        return 1

    # Compute quality score
    sum_price = 0.0
    sum_loads = 0
    sum_area = 0.0
    for br in bay_rects:
        sum_price += br['bt']['price']
        sum_loads += br['bt']['nLoads']
        sum_area += br['bt']['width'] * br['bt']['depth']

    if sum_loads > 0:
        current_eff = sum_price / sum_loads
    else:
        current_eff = 0.0

    Q = (current_eff ** (2.0 - (sum_area / wh_area))) if wh_area > 0 else 0
    print("STATUS: VALID")
    print(f"  Quality score Q = {Q:.2f}")
    print(f"  Total area covered = {sum_area:.0f}")
    print(f"  Warehouse area = {wh_area:.0f}")
    print(f"  Coverage = {sum_area / wh_area * 100:.1f}%")
    print(f"  Overall Efficiency (Price/Loads) = {current_eff:.4f}")
    print(f"  Area ratio = {sum_area / wh_area:.6f}")
    print(f"  Bays placed = {len(bay_rects)}")

    # Per-type breakdown
    type_counts = {}
    for br in bay_rects:
        tid = br['b']['typeId']
        if tid not in type_counts:
            type_counts[tid] = 0
        type_counts[tid] += 1

    print()
    print("Type breakdown:")
    for tid in sorted(type_counts):
        bt = bay_types[tid]
        cnt = type_counts[tid]
        print(f"  Type {tid}: {cnt} bays ({bt['width']}×{bt['depth']}+gap{bt['gap']}, h={bt['height']}, eff={bt['price']/bt['nLoads']:.1f})")

    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 6:
        print("Usage: python validator.py <warehouse.csv> <obstacles.csv> <ceiling.csv> <bays.csv> <solution.csv>")
        sys.exit(1)

    exit_code = validate(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
