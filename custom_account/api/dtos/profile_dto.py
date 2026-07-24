from pydantic import BaseModel, ConfigDict
from datetime import datetime, date

class ProfileUpdateInput(BaseModel):
    display_name: str | None = None
    avatar_url: str | None = None
    dob: datetime | None = None  
    gender: str | None = None
    language: str | None = None
    metadata: dict | None = None

    def to_dict(self, exclude_none: bool = True) -> dict:
        """
        Convert the model to a dictionary.
        
        Args:
            exclude_none (bool): Whether to exclude keys with None values. Defaults to True.
        
        Returns:
            dict: A dictionary representation of the model.
        """
        return self.model_dump(exclude_none=exclude_none)
    

class ProfilePublicOutput(BaseModel):
    display_name: str | None = None
    avatar_url: str | None = None
    dob: date | None = None
    gender: str | None = None
    language: str | None = None
    metadata: dict | None = None

    def to_dict(self, exclude_none: bool = True) -> dict:
        """
        Convert the model to a dictionary.
        
        Args:
            exclude_none (bool): Whether to exclude keys with None values. Defaults to True.
        
        Returns:
            dict: A dictionary representation of the model.
        """
        return self.model_dump(exclude_none=exclude_none)
    

class ProfileAdminOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    display_name: str | None = None
    avatar_url: str | None = None
    dob: date | None = None
    gender: str | None = None
    language: str | None = None
    metadata: dict | None = None

    def to_dict(self, exclude_none: bool = True) -> dict:
        """
        Convert the model to a dictionary.
        
        Args:
            exclude_none (bool): Whether to exclude keys with None values. Defaults to True.
        
        Returns:
            dict: A dictionary representation of the model.
        """
        return self.model_dump(exclude_none=exclude_none)