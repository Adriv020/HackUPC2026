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

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TIME_LIMIT = 28.0
#TIME_LIMIT = 120.0
EPS = 1e-6

# BayType tuple indices
BT_ID = 0; BT_W = 1; BT_D = 2; BT_H = 3; BT_G = 4; BT_NL = 5; BT_PR = 6; BT_TH = 7; BT_EFF = 8

# PlacedBay tuple indices
PB_TID = 0; PB_X = 1; PB_Y = 2; PB_R = 3; PB_X1 = 4; PB_Y1 = 5; PB_X2 = 6; PB_Y2 = 7
PB_AX1 = 8; PB_AY1 = 9; PB_AX2 = 10; PB_AY2 = 11


def make_bay_type(id_, w, d, h, g, nl, pr):
    th = h
    eff = pr / nl if nl > 0 else 1e18
    return (id_, w, d, h, g, nl, pr, th, eff)


def bay_footprint(bt, rotation):
    w = bt[BT_W]
    d = bt[BT_D] + bt[BT_G]  # gap on depth side (one end), forklift clearance
    if rotation == 0 or rotation == 180:
        return w, d
    return d, w


def make_placed_bay(bt, x, y, rotation):
    w_f, d_f = bay_footprint(bt, rotation)
    # Bay area B (no gap)
    if rotation == 0:
        ax1, ay1, ax2, ay2 = x, y, x + bt[BT_W], y + bt[BT_D]
    elif rotation == 90:
        ax1, ay1, ax2, ay2 = x + bt[BT_G], y, x + bt[BT_G] + bt[BT_D], y + bt[BT_W]
    elif rotation == 180:
        ax1, ay1, ax2, ay2 = x, y + bt[BT_G], x + bt[BT_W], y + bt[BT_G] + bt[BT_D]
    elif rotation == 270:
        ax1, ay1, ax2, ay2 = x, y, x + bt[BT_D], y + bt[BT_W]
    else:
        ax1, ay1, ax2, ay2 = x, y, x + w_f, y + d_f
    return (bt[BT_ID], x, y, rotation, x, y, x + w_f, y + d_f, ax1, ay1, ax2, ay2)


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
                 'slab_ys', 'slab_intervals')

    def __init__(self, verts):
        self.verts = verts
        self.area = polygon_area(verts)
        xs = [v[0] for v in verts]; ys = [v[1] for v in verts]
        self.min_x = min(xs); self.max_x = max(xs)
        self.min_y = min(ys); self.max_y = max(ys)
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
        if rx1 < self.min_x - EPS or rx2 > self.max_x + EPS:
            return False
        if ry1 < self.min_y - EPS or ry2 > self.max_y + EPS:
            return False
            
        check_ys = [ry1 + EPS, ry2 - EPS]
        for y in self.slab_ys:
            if ry1 + EPS < y < ry2 - EPS:
                check_ys.append(y)
                
        for y in check_ys:
            intervals = self._x_intervals(y)
            ok = False
            for xlo, xhi in intervals:
                if rx1 >= xlo - EPS and rx2 <= xhi + EPS:
                    ok = True; break
            if not ok:
                return False
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
                 'base_xs', 'base_ys', 'next_idx')

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

    def quality(self):
        if not self.active or self.sum_loads == 0: return 1e18
        current_eff = self.sum_price / self.sum_loads
        return current_eff ** (2.0 - (self.sum_area / self.wh_area))

    def feasible(self, bt, x, y, rot, excl=None):
        w_f, d_f = bay_footprint(bt, rot)
        x1, y1, x2, y2 = x, y, x + w_f, y + d_f
        
        # Bay area B (no gap)
        if rot == 0:
            ax1, ay1, ax2, ay2 = x, y, x + bt[BT_W], y + bt[BT_D]
        elif rot == 90:
            ax1, ay1, ax2, ay2 = x + bt[BT_G], y, x + bt[BT_G] + bt[BT_D], y + bt[BT_W]
        elif rot == 180:
            ax1, ay1, ax2, ay2 = x, y + bt[BT_G], x + bt[BT_W], y + bt[BT_G] + bt[BT_D]
        elif rot == 270:
            ax1, ay1, ax2, ay2 = x, y, x + bt[BT_D], y + bt[BT_W]
        else:
            ax1, ay1, ax2, ay2 = x, y, x + w_f, y + d_f

        if not self.wh.rect_inside(x1, y1, x2, y2):
            return False
        if self.ceiling.min_height(x1, x2) < bt[BT_TH] - EPS:
            return False
        cands = self.grid.query(x1, y1, x2, y2)
        for idx in cands:
            if idx == excl: continue
            if idx < 0:
                o = self.obs_rects[-(idx+2)]
                ow = min(x2, o[2]) - max(x1, o[0])
                oh = min(y2, o[3]) - max(y1, o[1])
                if ow > EPS and oh > EPS:
                    return False
            elif idx in self.active:
                b = self.bays[idx]
                # New bay's rack vs existing bay's footprint
                ow_a = min(ax2, b[PB_X2]) - max(ax1, b[PB_X1])
                oh_a = min(ay2, b[PB_Y2]) - max(ay1, b[PB_Y1])
                if ow_a > EPS and oh_a > EPS:
                    return False
                # Existing bay's rack vs new bay's footprint
                ow_b = min(x2, b[PB_AX2]) - max(x1, b[PB_AX1])
                oh_b = min(y2, b[PB_AY2]) - max(y1, b[PB_AY1])
                if ow_b > EPS and oh_b > EPS:
                    return False
        return True

    def add(self, bt, x, y, rot):
        pb = make_placed_bay(bt, x, y, rot)
        idx = self.next_idx; self.next_idx += 1
        self.bays[idx] = pb
        self.active.add(idx)
        self.grid.insert(idx, pb[PB_X1], pb[PB_Y1], pb[PB_X2], pb[PB_Y2])
        self.sum_price += bt[BT_PR]
        self.sum_loads += bt[BT_NL]
        self.sum_area += bt[BT_W] * bt[BT_D]
        return idx

    def remove(self, idx):
        pb = self.bays[idx]
        bt = self.bay_types[pb[PB_TID]]
        self.grid.remove(idx, pb[PB_X1], pb[PB_Y1], pb[PB_X2], pb[PB_Y2])
        self.active.discard(idx)
        self.sum_price -= bt[BT_PR]
        self.sum_loads -= bt[BT_NL]
        self.sum_area -= bt[BT_W] * bt[BT_D]
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

    # Pass 1: strip packing with small step
    for bt in sorted_bt:
        if time.time() - start > time_limit * 0.5: break
        for rot in [0, 90]:
            if time.time() - start > time_limit * 0.5: break
            w, d = bay_footprint(bt, rot)
            if w < 1 or d < 1: continue
            y = min_y
            while y + d <= max_y + EPS:
                if time.time() - start > time_limit * 0.5: break
                x = min_x
                while x + w <= max_x + EPS:
                    if state.feasible(bt, x, y, rot):
                        state.add(bt, x, y, rot)
                        total += 1
                        x += w  # jump past placed bay
                    else:
                        x += 50  # small step to find gaps
                y += d

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
            for rot in [0, 90]:
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

    T = max(1.0, best_q * 0.3) if best_q > 0 else 100.0
    alpha = 0.99997
    iters = 0
    no_imp = 0
    max_no_imp = 20000

    active_list = list(state.active)
    _random = random.random
    _exp = math.exp
    wh = state.wh

    while time.time() - start < time_limit:
        iters += 1
        n_active = len(active_list)
        r = _random()

        undo = None

        if n_active == 0:
            r = 0.0

        if r < 0.50:
            # === ADD ===
            tid = pick_type()
            bt = bay_types[tid]
            placed = False

            # Strategy 1: adjacent to existing bay (70% chance)
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

            # Strategy 2: random position
            if not placed:
                for rot in [0, 90]:
                    w, d = bay_footprint(bt, rot)
                    for _ in range(6):
                        tx = int(wh.min_x + _random() * max(1, wh.max_x - wh.min_x - w))
                        ty = int(wh.min_y + _random() * max(1, wh.max_y - wh.min_y - d))
                        if state.feasible(bt, tx, ty, rot):
                            idx = state.add(bt, tx, ty, rot)
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
                for rot in [0, 90]:
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

        elif r < 0.58:
            # === REMOVE ===
            if n_active > 0:
                ai = int(_random() * n_active)
                idx = active_list[ai]
                pb = state.remove(idx)
                active_list[ai] = active_list[-1]
                active_list.pop()
                undo = ('r', idx, pb, ai)

        elif r < 0.85:
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
                        for rot in [orot, 0, 90]:
                            w, d = bay_footprint(bt, rot)
                            trials = [
                                (ref[PB_X2], ref[PB_Y1]),
                                (ref[PB_X1] - w, ref[PB_Y1]),
                                (ref[PB_X1], ref[PB_Y2]),
                                (ref[PB_X1], ref[PB_Y1] - d),
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
                        rot = orot if _random() < 0.6 else (90 if orot == 0 else 0)
                        dx = int((_random() - 0.5) * 2000)
                        dy = int((_random() - 0.5) * 2000)
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

        else:
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
                    for rot in [orot, 0, 90, 180, 270]:
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
            if new_q < best_q:
                best_q = new_q
                best_snap = state.snapshot()
                no_imp = 0
            else:
                no_imp += 1
        else:
            _undo(state, undo, active_list)
            no_imp += 1

        T *= alpha

        if no_imp > max_no_imp:
            state.restore(best_snap)
            active_list = list(state.active)
            cur_q = best_q
            T = max(0.5, best_q * 0.05)
            no_imp = 0

        # Output telemetry every arbitrary block
        if iters % 100 == 0:
            print(f"[METRIC] {iters},{time.time()-start:.3f},{T:.2f},{cur_q:.2f},{best_q:.2f}")

    state.restore(best_snap)
    elapsed = time.time() - start
    print(f"  SA: {iters} iters ({iters/max(elapsed,0.001):.0f}/s), best Q={best_q:.2f}", file=sys.stderr)
    return best_q, iters


def _undo(state, info, active_list):
    kind = info[0]
    if kind == 'a':
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
        if not state.wh.rect_inside(x1, y1, x2, y2):
            print(f"  FAIL: bay {idx_i} outside warehouse", file=sys.stderr); ok = False
        if state.ceiling.min_height(x1, x2) < bt[BT_TH] - EPS:
            print(f"  FAIL: bay {idx_i} exceeds ceiling", file=sys.stderr); ok = False
        for oi, (ox1, oy1, ox2, oy2) in enumerate(state.obs_rects):
            ow = min(x2, ox2) - max(x1, ox1)
            oh = min(y2, oy2) - max(y1, oy1)
            if ow > EPS and oh > EPS:
                print(f"  FAIL: bay {idx_i} overlaps obstacle {oi} ({ow:.1f}x{oh:.1f})", file=sys.stderr)
                ok = False
        for j, (idx_j, bj) in enumerate(bays_list):
            if j <= i: continue
            # New bay's rack vs existing bay's footprint OR vice-versa
            ow_a = min(bi[PB_AX2], bj[PB_X2]) - max(bi[PB_AX1], bj[PB_X1])
            oh_a = min(bi[PB_AY2], bj[PB_Y2]) - max(bi[PB_AY1], bj[PB_Y1])
            ow_b = min(bi[PB_X2], bj[PB_AX2]) - max(bi[PB_X1], bj[PB_AX1])
            oh_b = min(bi[PB_Y2], bj[PB_AY2]) - max(bi[PB_Y1], bj[PB_AY1])
            if (ow_a > EPS and oh_a > EPS) or (ow_b > EPS and oh_b > EPS):
                print(f"  FAIL: bay {idx_i} overlaps bay {idx_j} (non-gap area)", file=sys.stderr)
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
            bt = state.bay_types[b[PB_TID]]
            w = bt[BT_W]
            d = bt[BT_D] + bt[BT_G]
            
            x_out = b[PB_X]
            y_out = b[PB_Y]
            rot = b[PB_R]
            
            # Map top-left aligned orthogonal representations to exact OBB mathematical pivoting
            if rot == 90:
                x_out += d
            elif rot == 180:
                x_out += w
                y_out += d
            elif rot == 270:
                y_out += w
                
            x_out = int(x_out) if x_out == int(x_out) else x_out
            y_out = int(y_out) if y_out == int(y_out) else y_out
            f.write(f"{b[PB_TID]}, {x_out}, {y_out}, {rot}\n")


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
    sa_iters = 0
    if remaining > 2.0:
        print(f"Phase 2: SA ({remaining:.1f}s)...", file=sys.stderr)
        _, sa_iters = sa(state, remaining)

    # Validate & output
    validate(state)
    q_final = state.quality()
    print(f"Final: {len(state.active)} bays, Q={q_final:.2f}, time={time.time()-t0:.1f}s", file=sys.stderr)
    print(f"[METRIC] {sa_iters},{time.time()-t0:.3f},0.0,{q_final:.2f},{q_final:.2f}")
    write_output(state, out_path)


if __name__ == '__main__':
    main()
