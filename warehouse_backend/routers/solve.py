from fastapi import APIRouter, File, UploadFile, Form

from services.solver_runner import run_solver

router = APIRouter()


@router.post("/solve")
async def solve(
    warehouse: UploadFile = File(...),
    obstacles: UploadFile = File(...),
    ceiling: UploadFile = File(...),
    types_of_bays: UploadFile = File(...),
    algorithm: str = Form("cpp"),
):
    return await run_solver(
        wh_csv=(await warehouse.read()).decode("utf-8"),
        obs_csv=(await obstacles.read()).decode("utf-8"),
        ceil_csv=(await ceiling.read()).decode("utf-8"),
        bays_csv=(await types_of_bays.read()).decode("utf-8"),
        algorithm=algorithm,
    )
