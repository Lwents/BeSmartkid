from datetime import datetime, timezone
from typing import TypedDict, Optional

from school.models import InvitationModel
from school.services.exceptions import InvalidOperation, DomainValidationError

class InvitationDict(TypedDict):
    id: Optional[int]
    classroom_id: int
    invite_code: str
    email: str
    created_by: int
    created_on: datetime
    expires_on: datetime
    status: str
    usage_limit: Optional[int]
    used_count: int


class InvitationDomain:
    """Entity representing a Classroom invitation."""
    VALID_STATUSES = ["pending", "accepted", "expired"]

    def __init__(self, id: Optional[int], classroom_id: int, invite_code: str,
                 created_by: int, expires_on: datetime, created_on: datetime,
                 status: str = "pending",
                 email: Optional[str] = None,
                 usage_limit: Optional[int] = None, 
                 used_count: int = 0,):
        self.id = id
        self.classroom_id = classroom_id
        self.invite_code = invite_code
        self.created_by = created_by
        self.expires_on = expires_on
        self.created_on = created_on
        self.status = status
        self.email = email
        self.usage_limit = usage_limit
        self.used_count = used_count
        self.validate()


    def validate(self):
        if not self.invite_code:
            raise DomainValidationError("invite_code is required")
        if not self.email:
            raise DomainValidationError("email is required")

    # --- Serialization ---
    def to_dict(self) -> InvitationDict:
        return {
            "id": self.id,
            "classroom_id": self.classroom_id,
            "invite_code": self.invite_code,
            "created_by": self.created_by,
            "expires_on": self.expires_on,
            "status": self.status,
            "email": self.email,
            "usage_limit": self.usage_limit,
            "used_count": self.used_count,
        }

    @classmethod
    def from_dict(cls, data: InvitationDict) -> "InvitationDomain":
        return cls(**data)
    

    # --- Mapping methods ---
    @classmethod
    def from_model(cls, invitation_model: InvitationModel) -> "InvitationDomain":
        # Support optional usage_limit/used_count fields if present on model
        usage_limit = getattr(invitation_model, "usage_limit", None)
        used_count = getattr(invitation_model, "used_count", 0)
        return cls(
            id=invitation_model.id,
            classroom_id=invitation_model.classroom,
            invite_code=invitation_model.invite_code,
            email=invitation_model.email,
            created_by=invitation_model.created_by,
            created_on=invitation_model.created_on,
            expires_on=invitation_model.expires_on,
            status=invitation_model.status.lower() if invitation_model.status else "pending",
            usage_limit=invitation_model.usage_limit,
            used_count=invitation_model.used_count,)


    # --- Business rules ---
    def is_valid(self) -> bool:
        if self.status != "pending":
            return False
        if datetime.astimezone() > self.expires_on:
            return False
        if self.usage_limit is not None and self.used_count >= self.usage_limit:
            return False
        return True
    
    def mark_used(self) -> None:
        """Increment usage count and expire if over limit."""
        if not self.is_valid():
            raise ValueError("Cannot use an invalid or expired invitation.")
        self.used_count += 1
        if self.usage_limit is not None and self.used_count >= self.usage_limit:
            self.status = "expired"

    def save(self, invitation_model: InvitationModel):
        invitation_model.status = self.status
        invitation_model.used_count = self.used_count
        invitation_model.save(update_fields=["status", "used_count"])


    def is_expired(self, now: Optional[datetime] = None) -> bool:
        if not self.expires_on:
            return False
        now = now or datetime.utcnow()
        return now > self.expires_on

    def can_be_used(self, now: Optional[datetime] = None) -> bool:
        if self.status != self.STATUS_PENDING:
            return False
        if self.is_expired(now):
            return False
        if self.usage_limit is not None and self.used_count >= self.usage_limit:
            return False
        return True

    def accept(self, now: Optional[datetime] = None) -> None:
        """Mark one usage of the invitation and update status accordingly."""
        now = now or datetime.utcnow()
        if self.status != self.STATUS_PENDING:
            raise InvalidOperation("Invitation is not pending")
        if self.is_expired(now):
            self.status = self.STATUS_EXPIRED
            raise InvalidOperation("Invitation expired")
        if self.usage_limit is not None and self.used_count >= self.usage_limit:
            raise InvalidOperation("Invitation usage limit reached")

        self.used_count += 1
        # Decide how to mark status: for single-use, mark accepted; for multi-use mark accepted when limit reached
        if self.usage_limit == 1 or (self.usage_limit is not None and self.used_count >= self.usage_limit):
            self.status = self.STATUS_ACCEPTED