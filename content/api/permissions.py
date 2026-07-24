from rest_framework.permissions import BasePermission, SAFE_METHODS
from custom_account.services import user_service

class IsAdminOrReadOnly(BasePermission):
    """
    Custom permission to allow admin users to perform any action, 
    and other users to have read-only access.
    """

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True

        return request.user and request.user.is_staff

class IsAuthorOrReadOnly(BasePermission):
    """
    Custom permission to only allow authors of an object to edit it.
    """

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True

        # Write permissions are only allowed to the author of the object.
        return obj.author == request.user

class CanReadExploration(BasePermission):
    """
    Custom permission to check if a user can read an exploration.
    """

    def has_object_permission(self, request, view, obj):
        # This is a placeholder. The actual logic will be implemented later.
        return True
