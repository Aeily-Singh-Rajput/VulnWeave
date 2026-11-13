
from typing import Literal
from pydantic import BaseModel, Field


AssetType = Literal[
    "account",
    "application",
    "server",
    "database",
    "device",
    "cloud",
    "service",
    "workstation",
]

SensitivityLevel = Literal[
    "low",
    "medium",
    "high",
    "critical",
]


class AssetInput(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    asset_type: AssetType
    description: str = Field(default="", max_length=1000)
    sensitivity: SensitivityLevel = "medium"
