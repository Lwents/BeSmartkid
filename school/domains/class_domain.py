from datetime import datetime
from typing import TypedDict, Optional

from school.models import ClassroomModel
from school.domains.membership_domain import MembershipDomain
from school.services.exceptions import InvalidOperation, DomainValidationError



class ClassDict(TypedDict):
    id: Optional[int]
    class_name: str
    status: str
    created_by: int
    created_on: datetime
    updated_on: datetime


class ClassroomDomain:
    """Entity representing a Classroom."""

    VALID_STATUSES = ["active", "archived", "deleted"]

    def __init__(self, id: Optional[int], name: str, created_by: int,
                 description: Optional[str] = None,
                 created_on: Optional[datetime] = None,
                 updated_on: Optional[datetime] = None,
                 status: str = "active"):
        self.id = id
        self.name = name
        self.description = description
        self.created_by = created_by
        self.created_on = created_on or datetime.astimezone()
        self.updated_on = updated_on or datetime.astimezone()
        self.status = status
        self.validate()


    # --- Validation ---
    def validate(self) -> None:
        if not self.name:
            raise ValueError("Classroom name is required.")
        if self.status not in self.VALID_STATUSES:
            raise ValueError(f"Invalid status: {self.status}")


    # --- Serialization ---
    def to_dict(self) -> ClassDict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "created_by": self.created_by,
            "created_on": self.created_on,
            "updated_on": self.updated_on,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: ClassDict) -> "ClassroomDomain":
        return cls(**data)


    # --- Mapping methods ---
    @classmethod
    def from_model(cls, class_model:ClassroomModel) -> "ClassroomDomain": # model -> domain
        """Convert a UserModel instance → UserDomain."""
        return cls(
            id=class_model.id,
            username=class_model.class_name,
            created_by = class_model.created_by,
            created_on = class_model.created_on,
            updated_on = class_model.updated_on,
            status = class_model.status,
        )


    # --- Business rules ---
    def can_accept_new_members(self) -> bool:
        """Archived classrooms cannot accept new members."""
        return self.status == "active"
    
    def ensure_active(self):
        if self.status != "active":
            raise InvalidOperation("Cannot operate on non-active classroom.")

    def ensure_has_instructor(self, memberships: list["MembershipDomain"]) -> None:
        """Ensure at least one instructor exists in this classroom."""
        instructors = [m for m in memberships if m.role in ["instructor", "co_instructor"] and m.is_active]
        if len(instructors) == 0:
            raise ValueError("Classroom must have at least one instructor.")
    

    # --- State transitions ---
    def archive(self) -> None:
        if self.status != "active":
            raise InvalidOperation("Only active classrooms can be archived.")
        self.status = "archived"

    def delete(self) -> None:
        if self.status == "deleted":
            raise InvalidOperation("Classroom already deleted")
        self.status = "deleted"

    def activate(self) -> None:
        if self.status == "active":
            return
        self.status = "active"

    def rename(self, new_name: str) -> None:
        if not new_name or not new_name.strip():
            raise DomainValidationError("Class name cannot be empty")
        self.class_name = new_name

