"""
Stateless solver pipeline: CSV strings → solver_flex → world JSON.
No MongoDB. Used by the /solve endpoint for the presentation demo.
"""
import asyncio
import sys
import time

from services.ceiling_service import get_ceiling_height
from services.csv_parser import (
    parse_bay_catalog,
    parse_ceiling,
    parse_obstacles,
    parse_warehouse,
)
from services.optimizer.solver import (
    Ceiling,
    State,
    Warehouse,
    aabb_from_corners,
    get_obb_corners,
    greedy,
    make_bay_type,
    post_process,
    sa,
)
from services.world_builder import build_ceiling_with_xto, compute_bounding_box

DEMO_TIME_LIMIT = 30.0  # seconds — keep it snappy for the live demo


# ---------------------------------------------------------------------------
# Synchronous solver — called via asyncio.to_thread
# ---------------------------------------------------------------------------

def _run(wh_verts, obstacles, ceil_pts, bay_types):
    t0 = time.time()
    wh = Warehouse(wh_verts)
    ceil = Ceiling(ceil_pts)
    state = State(bay_types, wh, obstacles, ceil)

    print(
        f"  [solver] {len(wh_verts)} verts, {len(obstacles)} obstacles, "
        f"{len(bay_types)} types, area={wh.area:.0f}",
        file=sys.stderr,
    )

    greedy_time = min(12.0, DEMO_TIME_LIMIT * 0.4)
    print(f"  [solver] Phase 1: greedy ({greedy_time:.0f}s)…", file=sys.stderr)
    greedy(state, greedy_time)

    remaining = DEMO_TIME_LIMIT - (time.time() - t0)
    if remaining > 4.0:
        print(f"  [solver] Phase 2: SA ({remaining - 3.0:.1f}s)…", file=sys.stderr)
        sa(state, remaining - 3.0)

    print(f"  [solver] Phase 3: post-processing…", file=sys.stderr)
    post_process(state)

    snap = state.snapshot()
    print(
        f"  [solver] done: {len(snap)} bays in {time.time() - t0:.1f}s",
        file=sys.stderr,
    )
    return snap


# ---------------------------------------------------------------------------
# Build world-compatible JSON from snapshot (no MongoDB IDs)
# ---------------------------------------------------------------------------

def _build_world(snapshot, perimeter, obstacles_raw, ceiling_raw, catalog):
    catalog_map = {b["typeId"]: b for b in catalog}
    bbox = compute_bounding_box(perimeter)
    ceiling_with_xto = build_ceiling_with_xto(ceiling_raw, bbox["maxX"])

    obstacles_with_height = [
        {**obs, "height": get_ceiling_height(ceiling_raw, obs["x"])}
        for obs in obstacles_raw
    ]

    rows_dict: dict[str, list] = {}
    total_revenue = 0.0

    for tid, x, y, rotation in snapshot:
        bt = catalog_map[tid]
        w = float(bt["width"])
        d = float(bt["depth"]) + float(bt["gap"])
        corners = get_obb_corners(float(x), float(y), w, d, float(rotation))
        x1, y1, x2, y2 = aabb_from_corners(corners)
        norm_rot = 0 if (x2 - x1) >= (y2 - y1) else 90

        total_revenue += bt["price"]
        row_id = f"row-{int(y1)}"
        rows_dict.setdefault(row_id, []).append({
            "bayId": f"bay-{tid}-{round(x1)}-{round(y1)}",
            "typeId": tid,
            "position": {"x": round(x1), "y": round(y1), "z": 0},
            "rotation": norm_rot,
            "dimensions": {
                "width": bt["width"],
                "depth": bt["depth"],
                "height": bt["height"],
            },
            "nLoads": bt["nLoads"],
            "price":  bt["price"],
        })

    total_bays = sum(len(v) for v in rows_dict.values())
    return {
        "warehouse": {"perimeter": perimeter, "boundingBox": bbox, "unit": "mm"},
        "obstacles": obstacles_with_height,
        "ceiling":   ceiling_with_xto,
        "rows":      [{"rowId": rid, "bays": bays} for rid, bays in rows_dict.items()],
        "summary":   {"totalBays": total_bays, "totalRevenue": total_revenue},
    }


# ---------------------------------------------------------------------------
# Public async entry point
# ---------------------------------------------------------------------------

async def run_solver(wh_csv: str, obs_csv: str, ceil_csv: str, bays_csv: str) -> dict:
    perimeter    = parse_warehouse(wh_csv)
    obstacles_raw = parse_obstacles(obs_csv)
    ceiling_raw  = parse_ceiling(ceil_csv)
    catalog      = parse_bay_catalog(bays_csv)

    wh_verts  = [(float(p["x"]), float(p["y"])) for p in perimeter]
    ceil_pts  = [(float(s["xFrom"]), float(s["maxHeight"])) for s in ceiling_raw]
    obs_tuples = [(float(o["x"]), float(o["y"]), float(o["width"]), float(o["depth"]))
                  for o in obstacles_raw]

    sorted_catalog = sorted(catalog, key=lambda b: b["typeId"])
    bay_types = [
        make_bay_type(
            b["typeId"],
            float(b["width"]), float(b["depth"]), float(b["height"]),
            float(b["gap"]), int(b["nLoads"]), float(b["price"]),
        )
        for b in sorted_catalog
    ]

    snapshot = await asyncio.to_thread(_run, wh_verts, obs_tuples, ceil_pts, bay_types)
    return _build_world(snapshot, perimeter, obstacles_raw, ceiling_raw, catalog)
