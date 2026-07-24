from typing import Type, Any
from pydantic import BaseModel
from rest_framework.exceptions import APIException
from rest_framework.views import APIView


class RoleBasedOutputMixin:
    """
    Choose the correct *output* DTO based on the requesting user.

    Expected on the view:
        - `output_dto_public`   → DTO class for normal users
        - `output_dto_admin`    → DTO class for staff / superuser
        - `output_dto_self`     → (optional) DTO for the owner of the object
    """

    output_dto_public: Type[BaseModel]
    output_dto_admin:  Type[BaseModel] | None = None
    output_dto_self:   Type[BaseModel] | None = None

    def _select_dto_class(self, instance: Any, request) -> Type[BaseModel]:
        """Return the DTO class that should be used for the current request."""
        user = request.user

        # 1. Admin / staff → full admin DTO
        if user.is_authenticated and user.is_staff and self.output_dto_admin:
            return self.output_dto_admin

        # 2. Owner of the object → self-DTO (if defined)
        if (hasattr(self, "output_dto_self")
                and self.output_dto_self
                and getattr(instance, "id", None) == getattr(user, "id", None)):
            return self.output_dto_self

        # 3. Fallback → public DTO
        return self.output_dto_public

    def _to_dto(self, instance: Any, request) -> BaseModel:
        """Convert a domain object → selected DTO."""
        dto_cls = self._select_dto_class(instance, request)
        # `from_orm` works with Django models, SQLAlchemy, etc.
        return dto_cls.model_validate(instance) # Pydantic v2

    def finalize_response(self, request, response, *args, **kwargs):
        """
        DRF calls this *after* the view returns a Response.
        We intercept and replace the payload if it contains {"instance": ...}
        """
        if isinstance(response.data, dict) and "instance" in response.data:
            domain_obj = response.data["instance"]
            dto_cls = self._select_dto_class(domain_obj, request)
            try:
                # Convert domain_obj to dict
                if hasattr(domain_obj, "model_dump"):  # It's already a Pydantic model
                    data = domain_obj.model_dump()
                elif hasattr(domain_obj, "__dict__"):  # Plain object / dataclass
                    data = domain_obj.__dict__
                else:
                    raise ValueError("Cannot convert domain object to dict")
            
                # Validate + create DTO
                dto_instance = dto_cls.model_validate(data)

                # Serialize to JSON
                response.data = dto_instance.model_dump()
            except Exception as e:
                raise APIException(f"DTO mapping failed: {e}")

        return APIView.finalize_response(self, request, response, *args, **kwargs)
