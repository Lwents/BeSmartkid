from pydantic import BaseModel
import uuid

class CourseBase(BaseModel):
    title: str
    description: str | None = None
    grade: str | None = None
    published: bool = False

class CoursePublicOutput(CourseBase):
    id: uuid.UUID

    class Config:
        orm_mode = True

class CourseAdminOutput(CoursePublicOutput):
    owner_id: uuid.UUID | None = None

class CourseInput(CourseBase):
    subject_id: uuid.UUID | None = None
