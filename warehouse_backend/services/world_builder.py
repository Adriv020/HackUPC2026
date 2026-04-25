from bson import ObjectId
from datetime import datetime

from services.ceiling_service import get_ceiling_height


def serialize_doc(obj):
    """Recursively convert ObjectIds to strings and rename _id → id."""
    if isinstance(obj, dict):
        return {("id" if k == "_id" else k): serialize_doc(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [serialize_doc(item) for item in obj]
    elif isinstance(obj, ObjectId):
        return str(obj)
    elif isinstance(obj, datetime):
        return obj.isoformat()
    return obj


def compute_bounding_box(perimeter: list[dict]) -> dict:
    """Handles negative coords (Case3 has x/y down to -8000)."""
    xs = [p["x"] for p in perimeter]
    ys = [p["y"] for p in perimeter]
    return {"minX": min(xs), "minY": min(ys), "maxX": max(xs), "maxY": max(ys)}


def build_ceiling_with_xto(ceiling_steps: list[dict], max_x: float) -> list[dict]:
    """Derives xTo for each step: next step's xFrom, or bounding-box maxX for the last."""
    sorted_steps = sorted(ceiling_steps, key=lambda s: s["xFrom"])
    result = []
    for i, step in enumerate(sorted_steps):
        x_to = sorted_steps[i + 1]["xFrom"] if i + 1 < len(sorted_steps) else max_x
        result.append({"xFrom": step["xFrom"], "xTo": x_to, "maxHeight": step["maxHeight"]})
    return result


async def build_world(scenario_id: str, db) -> dict | None:
    scenario = await db.scenarios.find_one({"_id": ObjectId(scenario_id)})
    if not scenario:
        return None

    project = await db.projects.find_one({"_id": scenario["projectId"]})
    if not project:
        return None

    perimeter = project["warehouse"]["perimeter"]
    bbox = compute_bounding_box(perimeter)
    ceiling_steps = project["ceiling"]

    ceiling_with_xto = build_ceiling_with_xto(ceiling_steps, bbox["maxX"])

    # Pre-compute obstacle height so the frontend doesn't need to query ceiling per obstacle
    obstacles_with_height = []
    for obs in project["obstacles"]:
        h = get_ceiling_height(ceiling_steps, obs["x"])
        obstacles_with_height.append({**obs, "height": h})

    cursor = db.bay_placements.find({"scenarioId": ObjectId(scenario_id)})
    placements = await cursor.to_list(None)

    rows_dict: dict[str, list] = {}
    for p in placements:
        rid = p["rowId"]
        if rid not in rows_dict:
            rows_dict[rid] = []
        rows_dict[rid].append({
            "bayId": str(p["_id"]),
            "typeId": p["typeId"],
            "position": p["position"],
            "rotation": p["rotation"],
            "dimensions": {
                "width": p["bayMeta"]["width"],
                "depth": p["bayMeta"]["depth"],
                "height": p["bayMeta"]["height"],
            },
            "nLoads": p["bayMeta"]["nLoads"],
            "price": p["bayMeta"]["price"],
        })

    rows = [{"rowId": rid, "bays": bays} for rid, bays in rows_dict.items()]

    return {
        "scenarioId": scenario_id,
        "projectId": str(scenario["projectId"]),
        "warehouse": {"perimeter": perimeter, "boundingBox": bbox, "unit": "mm"},
        "obstacles": obstacles_with_height,
        "ceiling": ceiling_with_xto,
        "rows": rows,
        "summary": {
            "totalBays": scenario.get("totalBays") or 0,
            "totalRevenue": scenario.get("totalRevenue") or 0,
        },
    }
