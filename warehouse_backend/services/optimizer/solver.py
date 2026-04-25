#!/usr/bin/env python3
"""
Simulated Annealing solver for the Mecalux Warehouse Bay Placement challenge.
HackUPC 2026.

Usage:
    python solver.py <warehouse.csv> <obstacles.csv> <ceiling.csv> <types_of_bays.csv> <output.csv>

Optimised for speed: spatial grid, incremental Q updates, slab-based polygon
containment, ceiling interval caching, dense greedy packing.
"""

import sys
import math
import random
import time
from typing import List, Tuple, Set, Dict

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

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
#TIME_LIMIT = 28.0
TIME_LIMIT = 180.0
EPS = 1e-6

# BayType tuple indices
BT_ID = 0; BT_W = 1; BT_D = 2; BT_H = 3; BT_G = 4; BT_NL = 5; BT_PR = 6; BT_TH = 7; BT_EFF = 8

# PlacedBay tuple indices
PB_TID = 0; PB_X = 1; PB_Y = 2; PB_R = 3; PB_X1 = 4; PB_Y1 = 5; PB_X2 = 6; PB_Y2 = 7; PB_CORNERS = 8


def make_bay_type(id_, w, d, h, g, nl, pr):
    th = h
    eff = pr / nl if nl > 0 else 1e18
    return (id_, w, d, h, g, nl, pr, th, eff)


def bay_footprint(bt, rotation):
    return bt[BT_W], bt[BT_D] + bt[BT_G]

def make_placed_bay(bt, x, y, rotation):
    w = bt[BT_W]
    d = bt[BT_D] + bt[BT_G]
    corners = get_obb_corners(x, y, w, d, rotation)
    min_x, min_y, max_x, max_y = aabb_from_corners(corners)
    return (bt[BT_ID], x, y, rotation, min_x, min_y, max_x, max_y, corners)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
def parse_warehouse(path):
    verts = []
    with open(path) as f:
        for ln in f:
            ln = ln.strip().replace('\r', '')
            if not ln: continue
            p = ln.split(',')
            if len(p) >= 2:
                try: verts.append((float(p[0]), float(p[1])))
                except ValueError: pass
    return verts


def parse_obstacles(path):
    obs = []
    with open(path) as f:
        for ln in f:
            ln = ln.strip().replace('\r', '')
            if not ln: continue
            p = ln.split(',')
            if len(p) >= 4:
                try: obs.append((float(p[0]), float(p[1]), float(p[2]), float(p[3])))
                except ValueError: pass
    return obs


def parse_ceiling(path):
    pts = []
    with open(path) as f:
        for ln in f:
            ln = ln.strip().replace('\r', '')
            if not ln: continue
            p = ln.split(',')
            if len(p) >= 2:
                try: pts.append((float(p[0]), float(p[1])))
                except ValueError: pass
    pts.sort()
    return pts


def parse_bay_types(path):
    bts = []
    with open(path) as f:
        for ln in f:
            ln = ln.strip().replace('\r', '')
            if not ln: continue
            p = ln.split(',')
            if len(p) >= 7:
                try:
                    bts.append(make_bay_type(
                        int(p[0]), float(p[1]), float(p[2]),
                        float(p[3]), float(p[4]), int(p[5]), float(p[6])))
                except ValueError: pass
    return bts


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------
def polygon_area(verts):
    n = len(verts)
    a = 0.0
    for i in range(n):
        j = (i + 1) % n
        a += verts[i][0] * verts[j][1] - verts[j][0] * verts[i][1]
    return abs(a) * 0.5


# ---------------------------------------------------------------------------
# Slab-decomposed axis-aligned polygon
# ---------------------------------------------------------------------------
class Warehouse:
    __slots__ = ('verts', 'area', 'min_x', 'min_y', 'max_x', 'max_y',
                 'slab_ys', 'slab_intervals', 'wall_angles')

    def __init__(self, verts):
        self.verts = verts
        self.area = polygon_area(verts)
        xs = [v[0] for v in verts]; ys = [v[1] for v in verts]
        self.min_x = min(xs); self.max_x = max(xs)
        self.min_y = min(ys); self.max_y = max(ys)
        
        # Precompute dominant wall angles
        angles = set()
        n = len(verts)
        for i in range(n):
            j = (i + 1) % n
            dx = verts[j][0] - verts[i][0]
            dy = verts[j][1] - verts[i][1]
            ang = math.degrees(math.atan2(dy, dx)) % 360.0
            angles.add(ang)
            angles.add((ang + 90) % 360.0)
            angles.add((ang + 180) % 360.0)
            angles.add((ang + 270) % 360.0)
        self.wall_angles = list(angles)

        uys = sorted(set(ys))
        self.slab_ys = uys
        self.slab_intervals = []
        for i in range(len(uys) - 1):
            y_mid = (uys[i] + uys[i+1]) * 0.5
            self.slab_intervals.append(self._x_intervals(y_mid))

    def _x_intervals(self, y):
        ints = []
        n = len(self.verts)
        for i in range(n):
            j = (i + 1) % n
            y1 = self.verts[i][1]; y2 = self.verts[j][1]
            if y1 == y2: continue
            if (y1 < y <= y2) or (y2 < y <= y1):
                x1 = self.verts[i][0]; x2 = self.verts[j][0]
                t = (y - y1) / (y2 - y1)
                ints.append(x1 + t * (x2 - x1))
        ints.sort()
        return [(ints[k], ints[k+1]) for k in range(0, len(ints)-1, 2)]

    def rect_inside(self, rx1, ry1, rx2, ry2):
        pass # Not used for flex, replaced by obb_inside

    def obb_inside(self, corners):
        min_x, min_y, max_x, max_y = aabb_from_corners(corners)
        if min_x < self.min_x - EPS or max_x > self.max_x + EPS:
            return False
        if min_y < self.min_y - EPS or max_y > self.max_y + EPS:
            return False
            
        def point_in_polygon(px, py):
            n = len(self.verts)
            inside = False
            j = n - 1
            for i in range(n):
                xi, yi = self.verts[i]
                xj, yj = self.verts[j]
                if ((yi > py) != (yj > py)):
                    x_int = xi + (py - yi) / (yj - yi) * (xj - xi) if yj != yi else xi
                    if px < x_int + EPS: inside = not inside
                j = i
            return inside

        for cx, cy in corners:
            if not point_in_polygon(cx, cy): return False
            
        # Check edge intersections
        for i in range(4):
            p1 = corners[i]; p2 = corners[(i+1)%4]
            n = len(self.verts)
            for j in range(n):
                w1 = self.verts[j]; w2 = self.verts[(j+1)%n]
                if segments_intersect(p1, p2, w1, w2): return False
                
        return True


# ---------------------------------------------------------------------------
# Ceiling (step function: each (x_i, h_i) means height is h_i from x_i onward)
# ---------------------------------------------------------------------------
class Ceiling:
    __slots__ = ('xs', 'hs', 'n')
    def __init__(self, pts):
        pts = sorted(pts)
        self.xs = [p[0] for p in pts]
        self.hs = [p[1] for p in pts]
        self.n = len(pts)

    def height_at(self, x):
        """Step function: find the last breakpoint <= x and return its height."""
        if self.n == 0: return 1e18
        if x < self.xs[0]: return self.hs[0]
        # Binary search for rightmost xs[i] <= x
        lo, hi = 0, self.n - 1
        while lo < hi:
            mid = (lo + hi + 1) >> 1
            if self.xs[mid] <= x: lo = mid
            else: hi = mid - 1
        return self.hs[lo]

    def min_height(self, x1, x2):
        """Minimum ceiling height over interval [x1, x2]."""
        if self.n == 0: return 1e18
        # The min is the minimum of all step values active in [x1, x2].
        # A step h_i is active in [x1,x2] if its interval [xs[i], xs[i+1]) overlaps [x1,x2].
        h = self.height_at(x1)  # step active at x1
        # Also check every breakpoint that falls in (x1, x2] — each starts a new step
        for i in range(self.n):
            if self.xs[i] > x2: break
            if self.xs[i] > x1:
                # This breakpoint is inside the interval, its step could be lower
                if self.hs[i] < h:
                    h = self.hs[i]
        return h


# ---------------------------------------------------------------------------
# Spatial grid
# ---------------------------------------------------------------------------
class Grid:
    __slots__ = ('ox', 'oy', 'cs', 'cols', 'rows', 'cells')
    def __init__(self, min_x, min_y, max_x, max_y, cell_size):
        self.ox = min_x; self.oy = min_y; self.cs = cell_size
        self.cols = max(1, int(math.ceil((max_x - min_x) / cell_size)))
        self.rows = max(1, int(math.ceil((max_y - min_y) / cell_size)))
        self.cells = {}

    def _range(self, x1, y1, x2, y2):
        c1 = max(0, int((x1 - self.ox) / self.cs))
        c2 = min(self.cols - 1, int((x2 - self.ox) / self.cs))
        r1 = max(0, int((y1 - self.oy) / self.cs))
        r2 = min(self.rows - 1, int((y2 - self.oy) / self.cs))
        return r1, r2, c1, c2

    def insert(self, idx, x1, y1, x2, y2):
        r1, r2, c1, c2 = self._range(x1, y1, x2, y2)
        cells = self.cells
        for r in range(r1, r2+1):
            for c in range(c1, c2+1):
                k = r * self.cols + c
                try: cells[k].add(idx)
                except KeyError: cells[k] = {idx}

    def remove(self, idx, x1, y1, x2, y2):
        r1, r2, c1, c2 = self._range(x1, y1, x2, y2)
        cells = self.cells
        for r in range(r1, r2+1):
            for c in range(c1, c2+1):
                k = r * self.cols + c
                s = cells.get(k)
                if s: s.discard(idx)

    def query(self, x1, y1, x2, y2):
        r1, r2, c1, c2 = self._range(x1, y1, x2, y2)
        cells = self.cells
        result = set()
        for r in range(r1, r2+1):
            for c in range(c1, c2+1):
                k = r * self.cols + c
                s = cells.get(k)
                if s: result.update(s)
        return result


# ---------------------------------------------------------------------------
# State: current placement of bays
# ---------------------------------------------------------------------------
class State:
    __slots__ = ('bay_types', 'wh', 'ceiling', 'obs_rects', 'grid',
                 'bays', 'active', 'sum_price', 'sum_loads', 'sum_area', 'wh_area',
                 'base_xs', 'base_ys', 'next_idx', 'candidate_corners', 'feasibility_cache')

    def __init__(self, bay_types, wh, obstacles, ceiling):
        self.bay_types = bay_types
        self.wh = wh
        self.ceiling = ceiling
        self.obs_rects = [(ox, oy, ox+ow, oy+od) for ox, oy, ow, od in obstacles]
        rng = max(wh.max_x - wh.min_x, wh.max_y - wh.min_y, 1.0)
        cs = max(50.0, rng / 80.0)
        self.grid = Grid(wh.min_x, wh.min_y, wh.max_x, wh.max_y, cs)
        # Use negative indices starting at -2 for obstacles to avoid collision
        # with default excl=None. Obstacle i -> grid idx -(i+2)
        for i, (ox1, oy1, ox2, oy2) in enumerate(self.obs_rects):
            self.grid.insert(-(i+2), ox1, oy1, ox2, oy2)
        self.bays = {}
        self.active = set()
        self.sum_price = 0.0
        self.sum_loads = 0.0
        self.sum_area = 0.0
        self.wh_area = wh.area
        self.next_idx = 0
        xs = set(v[0] for v in wh.verts)
        ys = set(v[1] for v in wh.verts)
        for ox, oy, ow, od in obstacles:
            xs.update([ox, ox+ow]); ys.update([oy, oy+od])
        self.base_xs = sorted(xs)
        self.base_ys = sorted(ys)
        
        self.candidate_corners = []
        self.feasibility_cache = {}
        self.update_candidate_positions()

    def update_candidate_positions(self):
        corners = set()
        for v in self.wh.verts:
            corners.add((v[0], v[1]))
        for ox, oy, ow, od in self.obs_rects:
            corners.update([(ox, oy), (ox+ow, oy), (ox, oy+od), (ox+ow, oy+od)])
        for idx in self.active:
            b = self.bays[idx]
            corners.update([(b[PB_X1], b[PB_Y1]), (b[PB_X2], b[PB_Y1]),
                            (b[PB_X1], b[PB_Y2]), (b[PB_X2], b[PB_Y2])])
        self.candidate_corners = list(corners)

    def quality(self):
        if not self.active or self.sum_loads == 0: return 1e18
        current_eff = self.sum_price / self.sum_loads
        return current_eff ** (2.0 - (self.sum_area / self.wh_area))

    def feasible(self, bt, x, y, rot, excl=None):
        r_x = round(x, 1)
        r_y = round(y, 1)
        r_rot = round(rot, 1)
        k = (bt[BT_ID], r_x, r_y, r_rot, excl)
        if k in self.feasibility_cache:
            return self.feasibility_cache[k]
        
        w = bt[BT_W]
        d = bt[BT_D] + bt[BT_G]
        corners = get_obb_corners(x, y, w, d, rot)
        x1, y1, x2, y2 = aabb_from_corners(corners)
        
        if not self.wh.obb_inside(corners):
            return False
            
        # Check ceiling
        if self.ceiling.min_height(x1, x2) < bt[BT_TH] - EPS:
            return False
            
        cands = self.grid.query(x1, y1, x2, y2)
        for idx in cands:
            if idx == excl: continue
            if idx < 0:
                o = self.obs_rects[-(idx+2)]
                obs_c = ((o[0],o[1]), (o[2],o[1]), (o[2],o[3]), (o[0],o[3]))
                if sat_overlap(corners, obs_c): return False
            elif idx in self.active:
                b = self.bays[idx]
                if sat_overlap(corners, b[PB_CORNERS]):
                    self.feasibility_cache[k] = False
                    return False
        self.feasibility_cache[k] = True
        return True

    def add(self, bt, x, y, rot):
        self.feasibility_cache.clear()
        pb = make_placed_bay(bt, x, y, rot)
        idx = self.next_idx; self.next_idx += 1
        self.bays[idx] = pb
        self.active.add(idx)
        self.grid.insert(idx, pb[PB_X1], pb[PB_Y1], pb[PB_X2], pb[PB_Y2])
        self.sum_price += bt[BT_PR]
        self.sum_loads += bt[BT_NL]
        self.sum_area += (pb[PB_X2] - pb[PB_X1]) * (pb[PB_Y2] - pb[PB_Y1])
        self.update_candidate_positions()
        return idx

    def remove(self, idx):
        self.feasibility_cache.clear()
        pb = self.bays[idx]
        bt = self.bay_types[pb[PB_TID]]
        self.grid.remove(idx, pb[PB_X1], pb[PB_Y1], pb[PB_X2], pb[PB_Y2])
        self.active.discard(idx)
        self.sum_price -= bt[BT_PR]
        self.sum_loads -= bt[BT_NL]
        self.sum_area -= (pb[PB_X2] - pb[PB_X1]) * (pb[PB_Y2] - pb[PB_Y1])
        self.update_candidate_positions()
        return pb

    def snapshot(self):
        return [(self.bays[i][PB_TID], self.bays[i][PB_X], self.bays[i][PB_Y], self.bays[i][PB_R])
                for i in self.active]

    def restore(self, snap):
        for idx in list(self.active):
            self.remove(idx)
        self.bays.clear()
        self.active.clear()
        self.next_idx = 0
        for tid, x, y, r in snap:
            self.add(self.bay_types[tid], x, y, r)


# ---------------------------------------------------------------------------
# Dense greedy packing
# ---------------------------------------------------------------------------
def greedy(state: State, time_limit: float):
    """
    Multi-pass greedy: for each bay type (sorted by efficiency) and each
    rotation, scan the warehouse in strips. After each full pass, recompute
    candidate positions from placed bay corners to fill gaps.
    """
    start = time.time()
    sorted_bt = sorted(state.bay_types, key=lambda b: b[BT_EFF])
    min_x, min_y = state.wh.min_x, state.wh.min_y
    max_x, max_y = state.wh.max_x, state.wh.max_y
    total = 0

    test_angles = state.wh.wall_angles if state.wh.wall_angles else []
    test_angles += [0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0]
    test_angles = list(set(test_angles))[:12]  # Expanded to 12 angles for grid occupancy scanning
    
    # Pass 1: strip packing with small step
    for bt in sorted_bt:
        if time.time() - start > time_limit * 0.5: break
        for rot in test_angles:
            if time.time() - start > time_limit * 0.5: break
            w, d = bay_footprint(bt, rot)
            if w < 1 or d < 1: continue
            y = min_y
            while y + d <= max_y + EPS:
                if time.time() - start > time_limit * 0.5: break
                x = min_x
                row_placed = False
                while x + w <= max_x + EPS:
                    if state.feasible(bt, x, y, rot):
                        state.add(bt, x, y, rot)
                        total += 1
                        x += w  # jump past placed bay
                        row_placed = True
                    else:
                        x += 50  # sliding window X
                if row_placed:
                    y += d
                else:
                    y += 50  # sliding window Y

    # Pass 2+: candidate-based filling using placed bay corners
    for _pass in range(5):
        if time.time() - start > time_limit: break
        placed_this_pass = 0
        # Gather candidate positions from all placed bay corners
        cxs = set(state.base_xs)
        cys = set(state.base_ys)
        for idx in state.active:
            b = state.bays[idx]
            cxs.add(b[PB_X1]); cxs.add(b[PB_X2])
            cys.add(b[PB_Y1]); cys.add(b[PB_Y2])
        sxs = sorted(cxs)
        sys_ = sorted(cys)

        for bt in sorted_bt:
            if time.time() - start > time_limit: break
            for rot in test_angles:
                w, d = bay_footprint(bt, rot)
                for y in sys_:
                    if time.time() - start > time_limit: break
                    for x in sxs:
                        if state.feasible(bt, x, y, rot):
                            state.add(bt, x, y, rot)
                            total += 1
                            placed_this_pass += 1
        if placed_this_pass == 0:
            break

    print(f"  Greedy: {total} bays, Q={state.quality():.2f}", file=sys.stderr)

def post_process(state: State):
    """
    Shrink & Shift optimization:
    Temporarily removes each bay and tests minor translation limits (±10 up to 100)
    and minor rotational shifts (±3 degrees). Keeps feasible shifts unconditionally 
    since type remains the same (efficiency is preserved).
    """
    shifts = [(-10, 0), (10, 0), (0, -10), (0, 10), (-20, 0), (20, 0), (0, -20), (0, 20),
              (-50, 0), (50, 0), (0, -50), (0, 50), (-100, 0), (100, 0), (0, -100), (0, 100)]
    rotations = [-3.0, 3.0, -6.0, 6.0, -15.0, 15.0, -30.0, 30.0]
    
    active_bays = list(state.active)
    for idx in active_bays:
        if idx not in state.active: continue
        pb = state.remove(idx)
        bt = state.bay_types[pb[PB_TID]]
        ox, oy, orot = pb[PB_X], pb[PB_Y], pb[PB_R]
        
        placed = False
        # Try shifts
        for dx, dy in shifts:
            if state.feasible(bt, ox + dx, oy + dy, orot):
                state.add(bt, ox + dx, oy + dy, orot)
                placed = True
                break
        
        # Try rotations if shift failed
        if not placed:
            for d_rot in rotations:
                nr = (orot + d_rot) % 360.0
                if state.feasible(bt, ox, oy, nr):
                    state.add(bt, ox, oy, nr)
                    placed = True
                    break
                    
        # Revert if no minor enhancement valid
        if not placed:
            state.add(bt, ox, oy, orot)
            
    # Final localized greedy to squeeze any missing bays into the new micro-gaps
    greedy(state, time_limit=3.0)


# ---------------------------------------------------------------------------
# Simulated Annealing
# ---------------------------------------------------------------------------
def sa(state: State, time_limit: float):
    start = time.time()
    best_q = state.quality()
    best_snap = state.snapshot()
    cur_q = best_q

    bay_types = state.bay_types
    n_types = len(bay_types)

    # Efficiency-weighted type selection
    weights = [bt[BT_NL] / bt[BT_PR] for bt in bay_types]
    wtot = sum(weights)
    cum_w = []
    s = 0.0
    for w in weights:
        s += w / wtot
        cum_w.append(s)
    cum_w[-1] = 1.0

    def pick_type():
        r = random.random()
        for i, c in enumerate(cum_w):
            if r <= c: return i
        return n_types - 1

    _random = random.random
    _exp = math.exp
    wh = state.wh
    active_list = list(state.active)
    
    # Initial T0 Evaluation Limit Calculation
    def sample_q_diffs(num=100):
        diffs = []
        for _ in range(num):
            tid = pick_type()
            bt = bay_types[tid]
            rot = state.wh.wall_angles[int(_random() * len(state.wh.wall_angles))] if state.wh.wall_angles and _random() < 0.5 else _random() * 360.0
            tx = wh.min_x + _random() * (wh.max_x - wh.min_x)
            ty = wh.min_y + _random() * (wh.max_y - wh.min_y)
            if state.feasible(bt, tx, ty, rot):
                idx = state.add(bt, tx, ty, rot)
                diffs.append(abs(state.quality() - cur_q))
                state.remove(idx)
        return diffs
        
    diffs = sample_q_diffs(100)
    if diffs:
        diffs.sort()
        T0 = max(1.0, 2.0 * diffs[len(diffs) // 2])
    else:
        T0 = max(1.0, best_q * 0.3) if best_q > 0 else 100.0
        
    T = T0
    max_iter = time_limit * 1000  # Estimate iterative bounds
    beta = max(0.0001, (T0 / max(1e-6, T0 * 0.01) - 1) / max_iter if max_iter > 0 else 0.0001)

    iters = 0
    no_imp = 0
    max_no_imp = 10000
    
    # [ADD, REMOVE, MOVE, SWAP, REPACK] Dynamic Window Probabilities
    move_probs = [0.4, 0.1, 0.3, 0.15, 0.05]
    move_attempts = [0]*5
    move_accepts = [0]*5
    
    def update_move_probs():
        nonlocal move_probs, move_attempts, move_accepts
        ratios = []
        for i in range(5):
            r = move_accepts[i] / move_attempts[i] if move_attempts[i] > 0 else 0.05
            ratios.append(max(0.05, r))
        tot = sum(ratios)
        move_probs = [r / tot for r in ratios]
        for i in range(5):
            move_attempts[i] = 0
            move_accepts[i] = 0

    def get_move_type(n_active):
        if n_active == 0: return 0
        rv = _random()
        s = 0.0
        for i, p in enumerate(move_probs):
            s += p
            if rv <= s: return i
        return 4

    active_list = list(state.active)
    _random = random.random
    _exp = math.exp
    wh = state.wh

    while time.time() - start < time_limit:
        iters += 1
        # Logarithmic cooling schedule instead of geometric
        T = T0 / (1.0 + beta * iters)
        
        n_active = len(active_list)
        m_type = get_move_type(n_active)
        move_attempts[m_type] += 1
        
        # Limit candidate positions update
        if iters % 1000 == 0:
            state.update_candidate_positions()
            
        if iters > 0 and iters % 500 == 0:
            update_move_probs()
            
        undo = None

        if m_type == 0:
            # === ADD ===
            tid = pick_type()
            bt = bay_types[tid]
            placed = False

            # Strategy 1: adjacent to existing bay or candidate anchors
            if n_active > 0 and _random() < 0.75:
                ref_idx = active_list[int(_random() * n_active)]
                ref = state.bays[ref_idx]
                rots = [0, 90] if _random() < 0.5 else [90, 0]
                for rot in rots:
                    w, d = bay_footprint(bt, rot)
                    trials = [
                        (ref[PB_X2], ref[PB_Y1]),
                        (ref[PB_X1] - w, ref[PB_Y1]),
                        (ref[PB_X1], ref[PB_Y2]),
                        (ref[PB_X1], ref[PB_Y1] - d),
                        (ref[PB_X2], ref[PB_Y2]),
                        (ref[PB_X1] - w, ref[PB_Y2]),
                        (ref[PB_X2], ref[PB_Y2] - d),
                        (ref[PB_X1] - w, ref[PB_Y1] - d),
                    ]
                    for tx, ty in trials:
                        if state.feasible(bt, tx, ty, rot):
                            idx = state.add(bt, tx, ty, rot)
                            active_list.append(idx)
                            undo = ('a', idx)
                            placed = True
                            break
                    if placed: break

            # Strategy 2: Base corners and candidates
            if not placed and state.candidate_corners:
                add_test_angles = state.wh.wall_angles if state.wh.wall_angles else [0.0, 90.0, 180.0, 270.0]
                add_test_angles = list(set(add_test_angles))[:8]
                random.shuffle(state.candidate_corners)
                for rot in add_test_angles:
                    for x, y in state.candidate_corners[:6]:
                        if state.feasible(bt, x, y, rot):
                            idx = state.add(bt, x, y, rot)
                            active_list.append(idx)
                            undo = ('a', idx)
                            placed = True
                            break
                    if placed: break

            # Strategy 3: base candidates
            if not placed:
                bxs = list(state.base_xs)
                bys = list(state.base_ys)
                random.shuffle(bxs)
                random.shuffle(bys)
                add_test_angles = state.wh.wall_angles if state.wh.wall_angles else [0.0, 90.0, 180.0, 270.0]
                add_test_angles = list(set(add_test_angles))[:8]
                for rot in add_test_angles:
                    for x in bxs[:6]:
                        for y in bys[:6]:
                            if state.feasible(bt, x, y, rot):
                                idx = state.add(bt, x, y, rot)
                                active_list.append(idx)
                                undo = ('a', idx)
                                placed = True
                                break
                        if placed: break
                    if placed: break

        elif m_type == 1:
            # === REMOVE ===
            if n_active > 0:
                ai = int(_random() * n_active)
                idx = active_list[ai]
                pb = state.remove(idx)
                active_list[ai] = active_list[-1]
                active_list.pop()
                undo = ('r', idx, pb, ai)

        elif m_type == 2:
            # === MOVE ===
            if n_active > 0:
                ai = int(_random() * n_active)
                idx = active_list[ai]
                pb = state.bays[idx]
                old_tid = pb[PB_TID]
                bt = bay_types[old_tid]
                ox, oy, orot = pb[PB_X], pb[PB_Y], pb[PB_R]

                state.remove(idx)

                moved = False
                # Try adjacent to another random bay
                if n_active > 1 and _random() < 0.5:
                    ri = int(_random() * (n_active - 1))
                    ref_idx = active_list[ri] if ri < ai else (active_list[ri + 1] if ri + 1 < n_active else active_list[0])
                    if ref_idx in state.active:
                        ref = state.bays[ref_idx]
                        ref_rot = ref[PB_R]
                        # Inherit neighbor rotation precisely or 90 offset strictly for tight geometric block packing
                        test_angles = [ref_rot, (ref_rot + 90) % 360.0, (ref_rot + 180) % 360.0, (ref_rot + 270) % 360.0]
                        for rot in test_angles:
                            w = bt[BT_W]; d = bt[BT_D] + bt[BT_G]
                            
                            # To align properly on edges without arbitrary AABB crushing, 
                            # we compute actual bounding sizes for the chosen rot
                            c_new = get_obb_corners(0, 0, w, d, rot)
                            min_nx, min_ny, max_nx, max_ny = aabb_from_corners(c_new)
                            span_x = max_nx - min_nx
                            span_y = max_ny - min_ny
                            
                            # Trials aligning the AABBs perfectly (without 1.6mm error)
                            trials = [
                                (ref[PB_X2], ref[PB_Y1]),
                                (ref[PB_X1] - span_x, ref[PB_Y1]),
                                (ref[PB_X1], ref[PB_Y2]),
                                (ref[PB_X1], ref[PB_Y1] - span_y),
                            ]
                            for tx, ty in trials:
                                if state.feasible(bt, tx, ty, rot):
                                    new_idx = state.add(bt, tx, ty, rot)
                                    active_list[ai] = new_idx
                                    undo = ('m', ai, old_tid, ox, oy, orot, new_idx)
                                    moved = True
                                    break
                            if moved: break

                if not moved:
                    for _ in range(8):
                        rand_val = _random()
                        if rand_val < 0.3 and state.wh.wall_angles:
                            # Strict pull to boundary constants
                            rot = state.wh.wall_angles[int(_random() * len(state.wh.wall_angles))]
                        elif rand_val < 0.6:
                            rot = orot + (_random() - 0.5) * 45.0  # Nudge rotation mathematically
                        else:
                            rot = _random() * 360.0  # Global scan
                            
                        # Quantize strictness bounding to 3-degree angular increments
                        rot = round(rot / 3.0) * 3.0 % 360.0
                        # Nudge position
                        dx = (_random() - 0.5) * 1000
                        dy = (_random() - 0.5) * 1000
                        tx, ty = ox + dx, oy + dy
                        if state.feasible(bt, tx, ty, rot):
                            new_idx = state.add(bt, tx, ty, rot)
                            active_list[ai] = new_idx
                            undo = ('m', ai, old_tid, ox, oy, orot, new_idx)
                            moved = True
                            break

                if not moved:
                    new_idx = state.add(bt, ox, oy, orot)
                    active_list[ai] = new_idx

        elif m_type == 3:
            # === SWAP type ===
            if n_active > 0:
                ai = int(_random() * n_active)
                idx = active_list[ai]
                pb = state.bays[idx]
                old_tid = pb[PB_TID]
                ox, oy, orot = pb[PB_X], pb[PB_Y], pb[PB_R]

                new_tid = pick_type()
                if new_tid != old_tid:
                    new_bt = bay_types[new_tid]
                    state.remove(idx)
                    swapped = False
                    new_test_angles = state.wh.wall_angles if state.wh.wall_angles else [0.0, 90.0, 180.0, 270.0]
                    new_test_angles = list(set([orot] + new_test_angles))[:8]
                    for rot in new_test_angles:
                        if state.feasible(new_bt, ox, oy, rot):
                            new_idx = state.add(new_bt, ox, oy, rot)
                            active_list[ai] = new_idx
                            undo = ('s', ai, old_tid, ox, oy, orot, new_idx)
                            swapped = True
                            break
                    if not swapped:
                        old_bt = bay_types[old_tid]
                        new_idx = state.add(old_bt, ox, oy, orot)
                        active_list[ai] = new_idx
                        
        elif m_type == 4:
            # === REPACK ===
            if n_active > 0:
                ai = int(_random() * n_active)
                idx = active_list[ai]
                pb = state.bays[idx]
                px_mid = (pb[PB_X1] + pb[PB_X2]) * 0.5
                py_mid = (pb[PB_Y1] + pb[PB_Y2]) * 0.5
                L = 4000.0  # localized square zone
                half_L = L * 0.5
                x_min, x_max = px_mid - half_L, px_mid + half_L
                y_min, y_max = py_mid - half_L, py_mid + half_L
                
                to_remove = []
                for b_idx in state.active:
                    b_rect = state.bays[b_idx]
                    if not (b_rect[PB_X2] < x_min or b_rect[PB_X1] > x_max or b_rect[PB_Y2] < y_min or b_rect[PB_Y1] > y_max):
                        to_remove.append(b_idx)
                
                saved_bays = [(b_idx, state.bays[b_idx]) for b_idx in to_remove]
                for b_idx in to_remove:
                    state.remove(b_idx)
                    try: active_list.remove(b_idx)
                    except ValueError: pass
                
                added = []
                step = L / 8.0 # Coarse scale to prevent extreme stalling
                sys_ = [y_min + i * step for i in range(9)]
                sxs = [x_min + i * step for i in range(9)]
                test_angles = state.wh.wall_angles if state.wh.wall_angles else [0.0, 90.0]
                test_angles = list(set(test_angles))[:4]
                for bt in sorted(bay_types, key=lambda x: x[BT_EFF])[:3]: # Only test top 3 cheapest
                    for rot in test_angles:
                        w, d = bay_footprint(bt, rot)
                        for y in sys_:
                            for x in sxs:
                                if state.feasible(bt, x, y, rot):
                                    n_idx = state.add(bt, x, y, rot)
                                    added.append(n_idx)
                                    active_list.append(n_idx)
                                    
                undo = ('repack', saved_bays, added)

        if undo is None:
            continue

        new_q = state.quality()
        delta = new_q - cur_q  # delta < 0 is GOOD (cost reduction)

        accept = True
        if delta > 0: # Worse step!
            if T > 1e-12:
                try:
                    accept = _random() < _exp(-delta / T)
                except OverflowError:
                    accept = False
            else:
                accept = False

        if accept:
            cur_q = new_q
            move_accepts[m_type] += 1
            if new_q < best_q:
                best_q = new_q
                best_snap = state.snapshot()
                no_imp = 0
            else:
                no_imp += 1
        else:
            _undo(state, undo, active_list)
            no_imp += 1

        # Skip `T *= alpha` explicitly replaced by Logarithmic cooling in header
        
        if no_imp > max_no_imp and T < 1e-5:
            # Terminate entirely on dry bottom curve dynamically
            break
        elif no_imp > max_no_imp:
            state.restore(best_snap)
            active_list.clear(); active_list.extend(state.active)
            cur_q = best_q
            T = max(1e-4, T0 * 0.05)
            no_imp = 0

        # Output telemetry every arbitrary block
        if iters % 100 == 0:
            print(f"[METRIC] {iters},{time.time()-start:.3f},{T:.2f},{cur_q:.2f},{best_q:.2f}")

    state.restore(best_snap)
    elapsed = time.time() - start
    print(f"  SA: {iters} iters ({iters/max(elapsed,0.001):.0f}/s), best Q={best_q:.2f}", file=sys.stderr)
    return best_q


def _undo(state, info, active_list):
    kind = info[0]
    if kind == 'repack':
        saved_bays, added = info[1], info[2]
        for a_idx in added:
            state.remove(a_idx)
        for b_idx, pb in saved_bays:
            state.bays[b_idx] = pb
            state.active.add(b_idx)
            state.grid.insert(b_idx, pb[PB_X1], pb[PB_Y1], pb[PB_X2], pb[PB_Y2])
            bt = state.bay_types[pb[PB_TID]]
            state.sum_price += bt[BT_PR]
            state.sum_loads += bt[BT_NL]
            state.sum_area += bt[BT_W] * bt[BT_D]
        state.update_candidate_positions()
        active_list.clear()
        active_list.extend(state.active)
    elif kind == 'a':
        state.remove(info[1])
        active_list.pop()
    elif kind == 'r':
        _, idx, pb, ai = info
        bt = state.bay_types[pb[PB_TID]]
        new_idx = state.add(bt, pb[PB_X], pb[PB_Y], pb[PB_R])
        active_list.append(new_idx)
        active_list[ai], active_list[-1] = active_list[-1], active_list[ai]
    elif kind in ('m', 's'):
        _, ai, old_tid, ox, oy, orot, new_idx = info
        state.remove(new_idx)
        bt = state.bay_types[old_tid]
        restored_idx = state.add(bt, ox, oy, orot)
        active_list[ai] = restored_idx


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate(state):
    bays_list = [(idx, state.bays[idx]) for idx in state.active]
    ok = True
    for i, (idx_i, bi) in enumerate(bays_list):
        bt = state.bay_types[bi[PB_TID]]
        x1, y1, x2, y2 = bi[PB_X1], bi[PB_Y1], bi[PB_X2], bi[PB_Y2]
        corners_i = bi[PB_CORNERS]
        if not state.wh.obb_inside(corners_i):
            print(f"  FAIL: bay {idx_i} outside warehouse", file=sys.stderr); ok = False
        if state.ceiling.min_height(x1, x2) < bt[BT_TH] - EPS:
            print(f"  FAIL: bay {idx_i} exceeds ceiling", file=sys.stderr); ok = False
        for oi, o in enumerate(state.obs_rects):
            obs_c = ((o[0],o[1]), (o[2],o[1]), (o[2],o[3]), (o[0],o[3]))
            if sat_overlap(corners_i, obs_c):
                print(f"  FAIL: bay {idx_i} overlaps obstacle {oi}", file=sys.stderr)
                ok = False
        for j, (idx_j, bj) in enumerate(bays_list):
            if j <= i: continue
            if sat_overlap(corners_i, bj[PB_CORNERS]):
                print(f"  FAIL: bay {idx_i} overlaps bay {idx_j}", file=sys.stderr)
                ok = False
    if ok:
        print(f"  Validation OK ({len(bays_list)} bays)", file=sys.stderr)
    return ok


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
def write_output(state, path):
    with open(path, 'w') as f:
        f.write("Id, X, Y, Rotation\n")
        for idx in sorted(state.active):
            b = state.bays[idx]
            # Output clean numeric values
            x_out = int(b[PB_X]) if b[PB_X] == int(b[PB_X]) else b[PB_X]
            y_out = int(b[PB_Y]) if b[PB_Y] == int(b[PB_Y]) else b[PB_Y]
            f.write(f"{b[PB_TID]}, {x_out}, {y_out}, {b[PB_R]}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    if len(sys.argv) < 6:
        print("Usage: python solver.py <warehouse> <obstacles> <ceiling> <types_of_bays> <output>",
              file=sys.stderr)
        sys.exit(1)

    t0 = time.time()
    wh_verts = parse_warehouse(sys.argv[1])
    obstacles = parse_obstacles(sys.argv[2])
    ceil_pts = parse_ceiling(sys.argv[3])
    bay_types = parse_bay_types(sys.argv[4])
    out_path = sys.argv[5]

    print(f"  Warehouse: {len(wh_verts)} verts, Obstacles: {len(obstacles)}, "
          f"Ceiling: {len(ceil_pts)} pts, Types: {len(bay_types)}", file=sys.stderr)

    for bt in sorted(bay_types, key=lambda b: b[BT_EFF]):
        print(f"    T{bt[BT_ID]}: {bt[BT_W]}x{bt[BT_D]} h={bt[BT_TH]} eff={bt[BT_EFF]:.1f}", file=sys.stderr)

    wh = Warehouse(wh_verts)
    ceil = Ceiling(ceil_pts)
    state = State(bay_types, wh, obstacles, ceil)
    print(f"  Warehouse area: {wh.area:.0f}", file=sys.stderr)

    # Phase 1: Greedy
    greedy_time = min(12.0, TIME_LIMIT * 0.4)
    print(f"Phase 1: Greedy ({greedy_time:.0f}s)...", file=sys.stderr)
    greedy(state, greedy_time)

    # Phase 2: SA
    remaining = TIME_LIMIT - (time.time() - t0)
    if remaining > 6.0:
        print(f"Phase 2: SA ({remaining - 5.0:.1f}s)...", file=sys.stderr)
        sa(state, remaining - 5.0)

    # Phase 3: Post-processing Shrink & Shift
    print(f"Phase 3: Post-processing...", file=sys.stderr)
    post_process(state)

    # Validate & output
    validate(state)
    q_final = state.quality()
    print(f"Final: {len(state.active)} bays, Q={q_final:.2f}, time={time.time()-t0:.1f}s", file=sys.stderr)
    write_output(state, out_path)


if __name__ == '__main__':
    main()
