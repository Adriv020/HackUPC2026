"""
Integrates the SA solver directly — no HTTP round-trip, no temp files.
The solver runs in asyncio.to_thread() because it is CPU-bound (~28 s).
"""
import asyncio
import sys
import time

from bson import ObjectId

from services.optimizer.solver import (
    Ceiling,
    State,
    Warehouse,
    TIME_LIMIT,
    greedy,
    make_bay_type,
    sa,
)
from websocket.manager import broadcast


# ---------------------------------------------------------------------------
# Data conversion: MongoDB document → solver's native tuple format
# ---------------------------------------------------------------------------

def _to_solver_inputs(project: dict):
    """
    Maps a MongoDB project doc to the types solver.py expects.
    Sorts bay catalog by typeId so list index == typeId
    (the solver uses direct list indexing: bay_types[tid]).
    """
    perimeter = project["warehouse"]["perimeter"]
    wh_verts = [(float(p["x"]), float(p["y"])) for p in perimeter]

    obstacles = [
        (float(o["x"]), float(o["y"]), float(o["width"]), float(o["depth"]))
        for o in project["obstacles"]
    ]

    # Ceiling: solver expects sorted (x_breakpoint, height) — already sorted in DB
    ceil_pts = [(float(s["xFrom"]), float(s["maxHeight"])) for s in project["ceiling"]]

    sorted_catalog = sorted(project["bayCatalog"], key=lambda b: b["typeId"])
    bay_types = [
        make_bay_type(
            b["typeId"],
            float(b["width"]), float(b["depth"]), float(b["height"]),
            float(b["gap"]), int(b["nLoads"]), float(b["price"]),
        )
        for b in sorted_catalog
    ]

    return wh_verts, obstacles, ceil_pts, bay_types


# ---------------------------------------------------------------------------
# Synchronous solver execution — called via asyncio.to_thread
# ---------------------------------------------------------------------------

def _run_solver(wh_verts, obstacles, ceil_pts, bay_types):
    """
    Black-box call: greedy phase → SA phase → snapshot.
    Returns list of (typeId, x, y, rotation) tuples.
    Internal logic of solver.py is untouched.
    """
    t0 = time.time()
    wh = Warehouse(wh_verts)
    ceil = Ceiling(ceil_pts)
    state = State(bay_types, wh, obstacles, ceil)

    print(
        f"  [solver] {len(wh_verts)} verts, {len(obstacles)} obstacles, "
        f"{len(bay_types)} types, area={wh.area:.0f}",
        file=sys.stderr,
    )

    greedy_time = min(12.0, TIME_LIMIT * 0.4)
    print(f"  [solver] Phase 1: greedy ({greedy_time:.0f}s)…", file=sys.stderr)
    greedy(state, greedy_time)

    remaining = TIME_LIMIT - (time.time() - t0)
    if remaining > 2.0:
        print(f"  [solver] Phase 2: SA ({remaining:.1f}s)…", file=sys.stderr)
        sa(state, remaining)

    snapshot = state.snapshot()
    print(
        f"  [solver] done: {len(snapshot)} bays in {time.time() - t0:.1f}s",
        file=sys.stderr,
    )
    return snapshot


# ---------------------------------------------------------------------------
# Persist solver output → MongoDB
# ---------------------------------------------------------------------------

async def _save_result(
    scenario_id: str, project: dict, snapshot: list, db
) -> tuple[int, float]:
    catalog = {b["typeId"]: b for b in project["bayCatalog"]}
    docs = []
    total_revenue = 0.0

    for tid, x, y, rotation in snapshot:
        # Normalize 180→0 and 270→90: rectangles have the same footprint at both
        # angles, and our API / Pydantic model only accepts Literal[0, 90].
        norm_rot = rotation % 180
        bay_type = catalog[tid]
        total_revenue += bay_type["price"]
        docs.append({
            "scenarioId": ObjectId(scenario_id),
            "projectId": project["_id"],   # already an ObjectId from find_one
            "rowId": f"row-{int(y)}",      # bays sharing Y sit in the same strip
            "typeId": tid,
            "position": {"x": round(float(x)), "y": round(float(y)), "z": 0},
            "rotation": norm_rot,
            "bayMeta": {
                "width":  bay_type["width"],
                "depth":  bay_type["depth"],
                "height": bay_type["height"],
                "nLoads": bay_type["nLoads"],
                "price":  bay_type["price"],
            },
        })

    if docs:
        await db.bay_placements.insert_many(docs)

    total_bays = len(docs)
    await db.scenarios.update_one(
        {"_id": ObjectId(scenario_id)},
        {"$set": {
            "status": "completed",
            "totalRevenue": total_revenue,
            "totalBays": total_bays,
        }},
    )

    await broadcast(scenario_id, {
        "event": "completed",
        "scenarioId": scenario_id,
        "totalBays": total_bays,
        "totalRevenue": total_revenue,
    })

    return total_bays, total_revenue


# ---------------------------------------------------------------------------
# Background task entry point — signature unchanged from the old HTTP version
# ---------------------------------------------------------------------------

async def trigger_optimizer(project_id: str, scenario_id: str, db) -> None:
    await db.scenarios.update_one(
        {"_id": ObjectId(scenario_id)},
        {"$set": {"status": "running"}},
    )

    project = await db.projects.find_one({"_id": ObjectId(project_id)})
    if not project:
        await db.scenarios.update_one(
            {"_id": ObjectId(scenario_id)},
            {"$set": {"status": "failed"}},
        )
        return

    try:
        wh_verts, obstacles, ceil_pts, bay_types = _to_solver_inputs(project)
        snapshot = await asyncio.to_thread(
            _run_solver, wh_verts, obstacles, ceil_pts, bay_types
        )
        total_bays, total_revenue = await _save_result(scenario_id, project, snapshot, db)
        print(
            f"  [optimizer] scenario {scenario_id}: "
            f"{total_bays} bays, revenue={total_revenue:.0f}",
            file=sys.stderr,
        )
    except Exception as exc:
        print(f"  [optimizer] ERROR scenario {scenario_id}: {exc}", file=sys.stderr)
        await db.scenarios.update_one(
            {"_id": ObjectId(scenario_id)},
            {"$set": {"status": "failed"}},
        )
