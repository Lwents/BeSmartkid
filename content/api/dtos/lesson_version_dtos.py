from pydantic import BaseModel
import uuid

class LessonVersionBase(BaseModel):
    version: int
    status: str = 'draft'
    content: dict = {}

class LessonVersionPublicOutput(LessonVersionBase):
    id: uuid.UUID
    author_id: uuid.UUID | None = None

    class Config:
        orm_mode = True

class LessonVersionInput(LessonVersionBase):
    lesson_id: uuid.UUID
