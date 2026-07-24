from pydantic import BaseModel
import uuid

class LessonBase(BaseModel):
    title: str
    position: int = 0
    content_type: str = 'lesson'
    published: bool = False

class LessonPublicOutput(LessonBase):
    id: uuid.UUID

    class Config:
        orm_mode = True

class LessonInput(LessonBase):
    module_id: uuid.UUID
