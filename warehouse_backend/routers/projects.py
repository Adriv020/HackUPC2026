from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from database import get_db
from services.csv_parser import parse_bay_catalog, parse_ceiling, parse_obstacles, parse_warehouse
from services.world_builder import serialize_doc

router = APIRouter()


def oid(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=404, detail="Invalid ID")


@router.post("/projects", status_code=201)
async def create_project(
    name: str = Form(...),
    warehouse: UploadFile = File(...),
    obstacles: UploadFile = File(...),
    ceiling: UploadFile = File(...),
    types_of_bays: UploadFile = File(...),
    db=Depends(get_db),
):
    perimeter = parse_warehouse((await warehouse.read()).decode("utf-8"))
    obs = parse_obstacles((await obstacles.read()).decode("utf-8"))
    ceil_steps = parse_ceiling((await ceiling.read()).decode("utf-8"))
    catalog = parse_bay_catalog((await types_of_bays.read()).decode("utf-8"))

    if len(perimeter) < 3:
        raise HTTPException(422, "Warehouse perimeter needs at least 3 vertices")
    if not ceil_steps:
        raise HTTPException(422, "Ceiling must have at least one step")

    doc = {
        "name": name,
        "createdAt": datetime.now(timezone.utc),
        "warehouse": {"perimeter": perimeter, "unit": "mm"},
        "obstacles": obs,
        "ceiling": ceil_steps,
        "bayCatalog": catalog,
    }
    result = await db.projects.insert_one(doc)
    return {"projectId": str(result.inserted_id), "name": name}


@router.get("/projects/{project_id}")
async def get_project(project_id: str, db=Depends(get_db)):
    project = await db.projects.find_one({"_id": oid(project_id)})
    if not project:
        raise HTTPException(404, "Project not found")
    return serialize_doc(project)
