from rest_framework import permissions


class IsTeacher(permissions.BasePermission):
    """Allow only teachers/instructors."""
    
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        # Check if user is instructor (role='instructor') or staff/admin
        return bool(
            request.user.is_staff or 
            (hasattr(request.user, 'role') and request.user.role == 'instructor')
        )

