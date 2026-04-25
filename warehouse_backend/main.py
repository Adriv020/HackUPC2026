from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import solve

app = FastAPI(title="WarehouseOS Solver API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(solve.router)
