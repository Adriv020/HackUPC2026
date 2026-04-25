import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from database import close_db, connect_db, create_indexes, get_db
from routers import heightmap, projects, scenarios
from websocket.change_stream import watch_placements
from websocket.manager import connected


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
    db = get_db()
    await create_indexes(db)
    task = asyncio.create_task(watch_placements(db))
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await close_db()


app = FastAPI(title="WarehouseOS API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router)
app.include_router(scenarios.router)
app.include_router(heightmap.router)


@app.websocket("/ws/scenario/{scenario_id}")
async def scenario_ws(websocket: WebSocket, scenario_id: str):
    await websocket.accept()
    connected[scenario_id].add(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep-alive ping loop
    except WebSocketDisconnect:
        connected[scenario_id].discard(websocket)
