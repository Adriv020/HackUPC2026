from typing import Literal, Optional

from pydantic import BaseModel, field_validator


class Point2D(BaseModel):
    x: float
    y: float


class Obstacle(BaseModel):
    x: float
    y: float
    width: float
    depth: float


class CeilingStep(BaseModel):
    x_from: float
    max_height: float


class BayType(BaseModel):
    type_id: int
    width: float
    depth: float
    height: float
    gap: float
    n_loads: int
    price: float


class BayPlacement(BaseModel):
    type_id: int
    row_id: str
    x: float
    y: float
    z: float = 0
    rotation: Literal[0, 90]

    @field_validator("x", "y", "z", mode="before")
    @classmethod
    def normalize_to_int_mm(cls, v):
        return round(float(v))


class ScenarioResult(BaseModel):
    placements: list[BayPlacement]


class ScenarioCreate(BaseModel):
    name: Optional[str] = None
