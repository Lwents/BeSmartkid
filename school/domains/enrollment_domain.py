from datetime import datetime
from typing import Any, Optional, TypedDict

from school.models import Enrollment

class EnrollmentDict(TypedDict):
    id: Optional[Any]
    classroom_id: Any
    student_id: Any
    role: str
    enrolled_at: datetime
    status: str

class EnrollmentDomain:
    STATUS_ACTIVE = "active"
    STATUS_PENDING = "pending"
    STATUS_DROPPED = "dropped"

    def __init__(self, id: Optional[Any], classroom_id: Any, student_id: Any, role: str = "student", enrolled_at: Optional[datetime] = None, status: str = STATUS_ACTIVE):
        self.id = id
        self.classroom_id = classroom_id
        self.student_id = student_id
        self.role = role
        self.enrolled_at = enrolled_at or datetime.utcnow()
        self.status = status
        self._validate()

    def _validate(self):
        if self.status not in {self.STATUS_ACTIVE, self.STATUS_PENDING, self.STATUS_DROPPED}:
            raise ValueError("Invalid enrollment status")

    @classmethod
    def from_model(cls, m: Enrollment) -> "EnrollmentDomain":
        return cls(
            id=getattr(m, "id", None),
            classroom_id=getattr(getattr(m, "classroom", None), "id", None) or getattr(m, "classroom_id", None) or getattr(m, "classroom", None),
            student_id=getattr(getattr(m, "student", None), "id", None) or getattr(m, "student_id", None) or getattr(m, "student", None),
            role=getattr(m, "role", "student"),
            enrolled_at=getattr(m, "enrolled_at", None),
            status=getattr(m, "status", EnrollmentDomain.STATUS_ACTIVE),
        )

    def drop(self):
        if self.status != self.STATUS_ACTIVE:
            raise ValueError("Can only drop an active enrollment")
        self.status = self.STATUS_DROPPED

    def to_dict(self) -> EnrollmentDict:
        return {
            "id": self.id,
            "classroom_id": self.classroom_id,
            "student_id": self.student_id,
            "role": self.role,
            "enrolled_at": self.enrolled_at,
            "status": self.status,
        }