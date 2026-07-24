from rest_framework import permissions


class IsStudent(permissions.BasePermission):
    """Allow only students."""
    
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        # Check if user is student (role='student') and not staff/admin
        return bool(
            not request.user.is_staff and 
            (not hasattr(request.user, 'role') or request.user.role == 'student')
        )


