from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional


class UserInput(BaseModel):
    username: str
    email: str
    password: str
    phone: str | None = None
    role: str 

    def to_dict(self, exclude_none: bool = True) -> dict:
        """
        Convert the model to a dictionary.
        
        Args:
            exclude_none (bool): Whether to exclude keys with None values. Defaults to True.
        
        Returns:
            dict: A dictionary representation of the model.
        """
        return self.model_dump(exclude_none=exclude_none)

class UserPublicOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    username: str
    email: str
    created_on: datetime
    phone: str | None
    role: Optional[str] = None

    def to_dict(self, exclude_none: bool = True) -> dict:
        """
        Convert the model to a dictionary.
        
        Args:
            exclude_none (bool): Whether to exclude keys with None values. Defaults to True.
        
        Returns:
            dict: A dictionary representation of the model.
        """
        return self.model_dump(exclude_none=exclude_none)

class UserAdminOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    created_on: Optional[datetime] = None
    updated_on: Optional[datetime] = None
    phone: str | None
    role: str
    is_active: bool
    last_login: Optional[datetime] = None

    def to_dict(self, exclude_none: bool = True) -> dict:
        """
        Convert the model to a dictionary.
        
        Args:
            exclude_none (bool): Whether to exclude keys with None values. Defaults to True.
        
        Returns:
            dict: A dictionary representation of the model.
        """
        return self.model_dump(exclude_none=exclude_none)


class UpdateUserInput(BaseModel):
    username: str | None = None
    email: str | None = None
    phone: str | None = None
    is_active: bool | None = None
    role: str | None = None

    def to_dict(self, exclude_none: bool = True) -> dict:
        """
        Convert the model to a dictionary.
        
        Args:
            exclude_none (bool): Whether to exclude keys with None values. Defaults to True.
        
        Returns:
            dict: A dictionary representation of the model.
        """
        return self.model_dump(exclude_none=exclude_none)
