from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException

from database import get_db
from models import ScenarioCreate, ScenarioResult
from services.ceiling_service import get_ceiling_height
from services.optimizer_client import trigger_optimizer
from services.world_builder import build_world, serialize_doc
from websocket.manager import broadcast

router = APIRouter()


def oid(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=404, detail="Invalid ID")


@router.post("/projects/{project_id}/scenarios", status_code=201)
async def create_scenario(
    project_id: str,
    bg: BackgroundTasks,
    body: Optional[ScenarioCreate] = Body(default=None),
    db=Depends(get_db),
):
    if not await db.projects.find_one({"_id": oid(project_id)}):
        raise HTTPException(404, "Project not found")

    name = (body.name if body and body.name else None) or \
        f"Run {datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"

    scenario_doc = {
        "projectId": oid(project_id),
        "name": name,
        "status": "pending",
        "createdAt": datetime.now(timezone.utc),
        "totalRevenue": None,
        "totalBays": None,
    }
    result = await db.scenarios.insert_one(scenario_doc)
    scenario_id = str(result.inserted_id)

    bg.add_task(trigger_optimizer, project_id, scenario_id, db)

    return {"scenarioId": scenario_id, "status": "pending", "name": name}


@router.get("/projects/{project_id}/scenarios")
async def list_scenarios(project_id: str, db=Depends(get_db)):
    if not await db.projects.find_one({"_id": oid(project_id)}):
        raise HTTPException(404, "Project not found")
    cursor = db.scenarios.find({"projectId": oid(project_id)})
    scenarios = await cursor.to_list(None)
    return {"scenarios": [serialize_doc(s) for s in scenarios]}


@router.get("/scenarios/{scenario_id}/status")
async def get_status(scenario_id: str, db=Depends(get_db)):
    scenario = await db.scenarios.find_one({"_id": oid(scenario_id)})
    if not scenario:
        raise HTTPException(404, "Scenario not found")
    return {
        "scenarioId": scenario_id,
        "status": scenario["status"],
        "totalBays": scenario.get("totalBays"),
        "totalRevenue": scenario.get("totalRevenue"),
    }


@router.post("/scenarios/{scenario_id}/result")
async def post_result(scenario_id: str, result: ScenarioResult, db=Depends(get_db)):
    scenario = await db.scenarios.find_one({"_id": oid(scenario_id)})
    if not scenario:
        raise HTTPException(404, "Scenario not found")

    project = await db.projects.find_one({"_id": scenario["projectId"]})
    if not project:
        raise HTTPException(404, "Project not found")

    catalog = {b["typeId"]: b for b in project["bayCatalog"]}
    ceiling_steps = project["ceiling"]
    docs = []
    total_revenue = 0

    for placement in result.placements:
        bay_type = catalog.get(placement.type_id)
        if bay_type is None:
            raise HTTPException(422, f"Unknown typeId: {placement.type_id}")

        ceiling_height = get_ceiling_height(ceiling_steps, placement.x)
        if bay_type["height"] > ceiling_height:
            raise HTTPException(
                422,
                f"typeId {placement.type_id} height {bay_type['height']}mm "
                f"exceeds ceiling {ceiling_height}mm at x={placement.x}",
            )

        total_revenue += bay_type["price"]
        docs.append({
            "scenarioId": oid(scenario_id),
            "projectId": scenario["projectId"],
            "rowId": placement.row_id,
            "typeId": placement.type_id,
            "position": {"x": placement.x, "y": placement.y, "z": placement.z},
            "rotation": placement.rotation,
            "bayMeta": {
                "width": bay_type["width"],
                "depth": bay_type["depth"],
                "height": bay_type["height"],
                "nLoads": bay_type["nLoads"],
                "price": bay_type["price"],
            },
        })

    if docs:
        await db.bay_placements.insert_many(docs)

    total_bays = len(docs)
    await db.scenarios.update_one(
        {"_id": oid(scenario_id)},
        {"$set": {"status": "completed", "totalRevenue": total_revenue, "totalBays": total_bays}},
    )

    await broadcast(scenario_id, {
        "event": "completed",
        "scenarioId": scenario_id,
        "totalBays": total_bays,
        "totalRevenue": total_revenue,
    })

    return {"status": "completed", "totalBays": total_bays, "totalRevenue": total_revenue}


@router.get("/scenarios/{scenario_id}/world")
async def get_world(scenario_id: str, db=Depends(get_db)):
    world = await build_world(scenario_id, db)
    if world is None:
        raise HTTPException(404, "Scenario not found")
    return world


@router.get("/scenarios/{scenario_id}/rows")
async def get_rows(scenario_id: str, db=Depends(get_db)):
    if not await db.scenarios.find_one({"_id": oid(scenario_id)}):
        raise HTTPException(404, "Scenario not found")

    cursor = db.bay_placements.find({"scenarioId": oid(scenario_id)}, {"rowId": 1})
    placements = await cursor.to_list(None)

    rows_dict: dict[str, int] = {}
    for p in placements:
        rid = p["rowId"]
        rows_dict[rid] = rows_dict.get(rid, 0) + 1

    rows = [{"rowId": rid, "bayCount": count} for rid, count in rows_dict.items()]
    return {"rows": rows}
