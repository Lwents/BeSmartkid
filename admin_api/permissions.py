from rest_framework.permissions import BasePermission


class IsAdmin(BasePermission):
    """Permission to allow only admin users."""
    
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.is_staff or (hasattr(request.user, 'role') and request.user.role == 'admin')











