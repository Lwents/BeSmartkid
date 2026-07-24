from pydantic import BaseModel
import uuid

class ExplorationBase(BaseModel):
    title: str
    language: str = 'vi'
    published: bool = False

class ExplorationPublicOutput(ExplorationBase):
    id: uuid.UUID

    class Config:
        orm_mode = True

class ExplorationAdminOutput(ExplorationPublicOutput):
    owner_id: uuid.UUID | None = None

class ExplorationInput(ExplorationBase):
    pass
