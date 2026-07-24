from rest_framework import permissions

class IsAdminOrReadOnly(permissions.BasePermission):
    """Allow unsafe methods only to admin users or teachers/instructors."""
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        if not request.user or not request.user.is_authenticated:
            return False
        # Allow admin or teacher/instructor
        return bool(
            request.user.is_staff or 
            (hasattr(request.user, 'role') and request.user.role in ['admin', 'instructor', 'teacher'])
        )


class IsOwnerOrAdmin(permissions.BasePermission):
    """
    Generic owner-or-admin permission.
    Must set view.lookup_object() or view.get_object() to return model instance with `student` or `owner` attribute.
    Fallback: allow if admin.
    """
    def has_object_permission(self, request, view, obj):
        if request.user and request.user.is_staff:
            return True
        # support objects with .student, .user, or .owner attribute
        owner = getattr(obj, "student", None) or getattr(obj, "user", None) or getattr(obj, "owner", None)
        if owner is None:
            return False
        return bool(owner == request.user)
