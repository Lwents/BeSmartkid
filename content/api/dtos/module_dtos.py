from pydantic import BaseModel
import uuid

class ModuleBase(BaseModel):
    title: str
    position: int = 0

class ModulePublicOutput(ModuleBase):
    id: uuid.UUID

    class Config:
        orm_mode = True

class ModuleInput(ModuleBase):
    course_id: uuid.UUID
