from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query

from database import get_db
from services.ceiling_service import get_ceiling_height
from services.world_builder import build_ceiling_with_xto, compute_bounding_box

router = APIRouter()


def oid(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=404, detail="Invalid ID")


@router.get("/projects/{project_id}/heightmap")
async def get_heightmap(project_id: str, db=Depends(get_db)):
    project = await db.projects.find_one({"_id": oid(project_id)})
    if not project:
        raise HTTPException(404, "Project not found")

    bbox = compute_bounding_box(project["warehouse"]["perimeter"])
    steps = build_ceiling_with_xto(project["ceiling"], bbox["maxX"])

    return {
        "type": "step_function",
        "steps": steps,
        "queryEndpoint": f"/projects/{project_id}/heightmap/query?x={{x}}",
    }


@router.get("/projects/{project_id}/heightmap/query")
async def query_heightmap(
    project_id: str,
    x: float = Query(..., description="X coordinate in mm"),
    db=Depends(get_db),
):
    project = await db.projects.find_one({"_id": oid(project_id)})
    if not project:
        raise HTTPException(404, "Project not found")

    height = get_ceiling_height(project["ceiling"], x)
    return {"x": x, "maxHeight": height}
