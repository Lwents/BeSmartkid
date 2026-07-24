import re
from typing import TypedDict, Optional, Dict, Any
from datetime import datetime, date

from custom_account.models import Profile


class ProfileDict(TypedDict):
    """Dataclass representing the ProfileSettings object."""
    user_id: int
    display_name: Optional[str]
    avatar_url: Optional[str]
    dob: Optional[datetime.date]
    gender: Optional[str] 
    language: str = "vi"
    meta: Optional[Dict[str, Any]]


class ProfileDomain:
    """Domain object for user profile."""

    def __init__(
        self,
        user_id: int,
        display_name: Optional[str] = None,
        avatar_url: Optional[str] = None,
        dob: Optional[datetime.date] = None,
        gender: Optional[str] = None,
        language: str = "vi",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.user_id = user_id
        self.display_name = display_name
        self.avatar_url = avatar_url
        self.dob = dob
        self.gender = gender
        self.language = language
        self.metadata = metadata or {}


    def validate(self):
        if self.user_id is None:
            raise ValueError("user_id is required")

        if isinstance(self.dob, datetime):
            self.dob = self.dob.date()

        if self.dob is not None and self.dob > date.today():
            raise ValueError("Date of birth cannot be in the future.")

        if self.language not in ["vietnamese", "english"]:
            raise ValueError("Unsupported language.")


    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "display_name": self.display_name,
            "avatar_url": self.avatar_url,
            "dob": self.dob,
            "gender": self.gender,
            "language": self.language,
            "metadata": self.metadata or {},
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProfileDomain":
        return cls(
            user_id=data["user_id"],
            display_name=data.get("display_name"),
            avatar_url=data.get("avatar_url"),
            dob=data.get("dob"),
            gender=data.get("gender"),
            language=data.get("language", "vi"),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def from_model(cls, model: Profile) -> "ProfileDomain":
        return cls(
            user_id=model.user_id,
            display_name=model.display_name,
            avatar_url=model.avatar_url,
            dob=model.dob,
            gender=model.gender,
            language=model.language,
            metadata=model.metadata,
        )
    
    
    
