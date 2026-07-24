from pydantic import BaseModel
import uuid

class SubjectBase(BaseModel):
    title: str
    slug: str

class SubjectPublicOutput(SubjectBase):
    id: uuid.UUID

    class Config:
        orm_mode = True

class SubjectInput(SubjectBase):
    pass
