import os
from typing import Optional

from dotenv import load_dotenv
from pymongo import AsyncMongoClient

load_dotenv()

# Required env vars: MONGODB_URL, DATABASE_NAME, OPTIMIZER_URL, BACKEND_URL
MONGODB_URL: str = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DATABASE_NAME: str = os.getenv("DATABASE_NAME", "warehouseos")

_client: Optional[AsyncMongoClient] = None
_db = None


async def connect_db() -> None:
    global _client, _db
    _client = AsyncMongoClient(MONGODB_URL)
    _db = _client[DATABASE_NAME]


def close_db() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None


def get_db():
    return _db


async def create_indexes(db) -> None:
    await db.bay_placements.create_index([("scenarioId", 1)])
    await db.bay_placements.create_index([("projectId", 1), ("scenarioId", 1)])
    await db.scenarios.create_index([("projectId", 1)])
