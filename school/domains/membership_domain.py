from datetime import datetime
from typing import TypedDict, Optional

from school.models import MembershipModel
from school.services.exceptions import InvalidOperation



class MembershipDict(TypedDict):
    id: Optional[int]
    classroom_id: int
    user_id: int
    role: str
    joined_on: datetime
    is_active: bool


class MembershipDomain:
    """Value object representing a user membership inside a classroom."""

    VALID_ROLES = ["student", "instructor", "co-instructor"]

    def __init__(self, id: Optional[int], classroom_id: int, user_id: int,
                 role: str, joined_on: Optional[datetime] = None,
                 is_active: bool = True):
        self.id = id
        self.classroom_id = classroom_id
        self.user_id = user_id
        self.role = role
        self.joined_on = joined_on or datetime.astimezone()
        self.is_active = is_active
        self.validate()


    # --- Validation ---
    def validate(self) -> None:
        if self.role not in self.VALID_ROLES:
            raise ValueError(f"Invalid role: {self.role}")


    # --- Serialization ---
    def to_dict(self) -> MembershipDict:
        return {
            "classroom_id": self.classroom_id,
            "user_id": self.user_id,
            "role": self.role,
            "joined_on": self.joined_on,
            "is_active": self.is_active,
        }

    @classmethod
    def from_dict(cls, data: MembershipDict) -> "MembershipDomain":
        return cls(**data)
    

    # --- Mapping methods ---
    @classmethod
    def from_model(cls, membership_model: MembershipModel) -> "MembershipDomain":
        user_id = membership_model.student.id
        return cls(
            id=membership_model.id,
            classroom_id=membership_model.classroom,
            user_id=membership_model.student,
            role=membership_model.role.lower() if membership_model.role else "student",
            joined_on=membership_model.joined_on,
            is_active=membership_model.is_active,
    )


    # --- Business rules ---
    def can_leave_classroom(self, pending_lessons: int) -> bool:
        """Student cannot leave if they have unfinished lessons/quizzes."""
        if self.role == "student" and pending_lessons > 0:
            return False
        return True

    def can_be_removed(self, total_instructors: int) -> bool:
        """Instructor cannot be removed if they are the last one."""
        if self.role in ["instructor", "co_instructor"] and total_instructors <= 1:
            return False
        return True
    

    def deactivate(self):
        self.is_active = False

    def activate(self):
        self.is_active = True