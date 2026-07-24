import uuid
from typing import TypedDict, Optional, Dict, Any
from django.utils import timezone

from custom_account.models import ParentalConsent


class ParentalConsentDict(TypedDict):
    """Dataclass representing the UserSettings object."""
    parent_id: int
    child_id: str
    id: Optional[uuid.UUID]
    consented_at: Optional[timezone.datetime] 
    scopes: Optional[list[str]] 
    revoked_at: Optional[timezone.datetime] 
    metadata: Optional[Dict[str, Any]] 


class ParentalConsentDomain:
    """Domain object for parental consent."""

    def __init__(
        self,
        parent_id: int,
        child_id: int,
        id: Optional[uuid.UUID] = None,
        consented_at: Optional[timezone.datetime] = None,
        scopes: Optional[list[str]] = None,
        revoked_at: Optional[timezone.datetime] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.id = id or uuid.uuid4()
        self.parent_id = parent_id
        self.child_id = child_id
        self.consented_at = consented_at or timezone.now()
        self.scopes = scopes or []
        self.revoked_at = revoked_at
        self.metadata = metadata or {}

    def validate(self):
        if not self.parent_id or not self.child_id:
            raise ValueError("Both parent and child are required.")

        if self.parent_id == self.child_id:
            raise ValueError("Parent and child cannot be the same user.")
        
        if not self.scopes or len(self.scopes) == 0:
            raise ValueError("At least one scope must be provided")


    def revoke(self):
        if self.revoked_at:
            raise ValueError("Consent already revoked.")
        self.revoked_at = timezone.now()

    @property
    def is_revoked(self) -> bool:
        """Returns True if consent has been revoked (revoked_at is set)"""
        return self.revoked_at is not None

    def is_active(self) -> bool:
        return self.revoked_at is None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "parent_id": self.parent_id,
            "child_id": self.child_id,
            "consented_at": self.consented_at,
            "scopes": self.scopes,
            "revoked_at": self.revoked_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ParentalConsentDomain":
        return cls(
            id=data.get("id"),
            parent_id=data["parent_id"],
            child_id=data["child_id"],
            consented_at=data.get("consented_at"),
            scopes=data.get("scopes", []),
            revoked_at=data.get("revoked_at"),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def from_model(cls, model: ParentalConsent) -> "ParentalConsentDomain":
        return cls(
            id=model.id,
            parent_id=model.parent_id,
            child_id=model.child_id,
            consented_at=model.consented_at,
            scopes=model.scopes,
            revoked_at=model.revoked_at,
            metadata=model.metadata,
        )
