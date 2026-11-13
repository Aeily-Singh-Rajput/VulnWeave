
from pydantic import BaseModel, Field


class RelationshipInput(BaseModel):
    source_id: int = Field(gt=0)
    target_id: int = Field(gt=0)
    permission_id: int | None = None
    description: str = Field(default="", max_length=1000)
