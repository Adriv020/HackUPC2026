from fastapi import HTTPException

from models import BayPlacement


def get_ceiling_height(ceiling_steps: list[dict], x: float) -> float:
    """
    Step-function lookup — NOT interpolated. Steps must be sorted by xFrom ascending.
    Handles negative X values (Case3 starts at -7500).
    If x is before all breakpoints, returns the first step's height.
    """
    sorted_steps = sorted(ceiling_steps, key=lambda s: s["xFrom"])
    height = sorted_steps[0]["maxHeight"]
    for step in sorted_steps:
        if x >= step["xFrom"]:
            height = step["maxHeight"]
        else:
            break
    return height


def validate_bay_against_ceiling(bay: BayPlacement, project: dict) -> None:
    ceiling_height = get_ceiling_height(project["ceiling"], bay.x)
    catalog = {b["typeId"]: b for b in project["bayCatalog"]}
    bay_type = catalog.get(bay.type_id)
    if bay_type is None:
        raise HTTPException(status_code=422, detail=f"Unknown typeId: {bay.type_id}")
    if bay_type["height"] > ceiling_height:
        raise HTTPException(
            status_code=422,
            detail=(
                f"typeId {bay.type_id} height {bay_type['height']}mm "
                f"exceeds ceiling {ceiling_height}mm at x={bay.x}"
            ),
        )
