from django.core.exceptions import ObjectDoesNotExist
from rest_framework.permissions import BasePermission
from custom_account.services import user_service

class RestrictRoles(BasePermission):
    """
    Custom permission to restrict access based on user roles.
    """

    def __init__(self, allow_roles):
        self.allow_roles = allow_roles

    def has_permission(self, request, view):
        # Allow access if the user is an admin
        if not request.user or not request.user.is_authenticated:
            return False
        
        if request.user.role == 'admin':
                return True

        # Fetch user_domain from service layer
        user_domain = user_service.get_user(request.user.id)
        if not user_domain:
            return False
        
        # Check if the user's role is in the allowed roles
        return user_domain.role in self.allow_roles
    
class IsAdminOrSelf(BasePermission):
    """
    Custom permission to allow access if the user is an admin or accessing their own data.
    """

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        return True
    
    def has_object_permission(self, request, view, obj):
        """
        Custom permission to allow access if the user is an admin or accessing their own data.
        """

        if request.user.is_staff:  # OR: if request.user.role == "admin":
            return True
       
       # Allow users accessing their own data
        return obj.id == request.user.id
    

class IsSelf(BasePermission):
    def has_object_permission(self, request, view, obj):
        # obj ở đây là instance của UserModel
        return obj.id == request.user.id


class IsOwnerOrAdmin(BasePermission):
    """
    Custom permission to allow access if the user is an admin or the owner of the object.
    """

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        return True

    def has_object_permission(self, request, view, obj):
        if request.user.is_staff or request.user.is_superuser:
            return True
        return self._is_owned_by_user(obj, request.user)

    def _is_owned_by_user(self, obj, user, visited=None):
        if obj is None or not user.is_authenticated:
            return False
        visited = visited or set()
        obj_id = getattr(obj, 'pk', None) or id(obj)
        cache_key = (type(obj), obj_id)
        if cache_key in visited:
            return False
        visited.add(cache_key)

        # direct owner/id attributes to inspect
        direct_id_fields = (
            'owner_id',
            'user_id',
            'student_id',
            'teacher_id',
            'created_by_id',
            'creator_id',
        )
        for field in direct_id_fields:
            if getattr(obj, field, None) == user.id:
                return True

        direct_obj_fields = (
            'owner',
            'user',
            'student',
            'teacher',
            'created_by',
            'creator',
        )
        for field in direct_obj_fields:
            target = getattr(obj, field, None)
            if target is not None and getattr(target, 'id', None) == user.id:
                return True

        # check related objects that may carry ownership info (e.g. course->owner)
        related_fields = ('course', 'module', 'lesson', 'parent', 'profile')
        for field in related_fields:
            if hasattr(obj, field):
                try:
                    related = getattr(obj, field)
                except ObjectDoesNotExist:
                    continue
                if related is None:
                    continue
                if self._is_owned_by_user(related, user, visited):
                    return True

        return False
