from pydantic import BaseModel
import uuid

class ContentBlockBase(BaseModel):
    type: str
    position: int = 0
    payload: dict = {}

class ContentBlockPublicOutput(ContentBlockBase):
    id: uuid.UUID

    class Config:
        orm_mode = True

class ContentBlockInput(ContentBlockBase):
    lesson_version_id: uuid.UUID
