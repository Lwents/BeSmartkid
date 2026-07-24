from typing import Any, Optional, TypedDict

from school.models import SchoolModel


class SchoolDict(TypedDict):
    id: Optional[Any]
    name: str
    code: Optional[str]
    metadata: dict


class SchoolDomain:
    """Domain entity representing a School (lightweight)."""

    def __init__(self, id: Optional[Any], name: str, code: Optional[str] = None, metadata: Optional[dict] = None):
        self.id = id
        self.name = name
        self.code = code
        self.metadata = metadata or {}
        self._validate()

    def _validate(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("School name is required")

    def to_dict(self) -> SchoolDict:
        return {"id": self.id, "name": self.name, "code": self.code, "metadata": self.metadata}

    @classmethod
    def from_model(cls, model: SchoolModel) -> "SchoolDomain":
        return cls(
            id=getattr(model, "id", None),
            name=getattr(model, "name", ""),
            code=getattr(model, "code", None),
            metadata=getattr(model, "metadata", {}) or {},
        )