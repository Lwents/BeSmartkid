# ai_personalization/permissions.py
"""
Custom permissions for personalization API.
"""
from rest_framework import permissions


class IsStudent(permissions.BasePermission):
    """Permission for student users."""
    
    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            not request.user.is_staff
        )


class IsTeacherOrAdmin(permissions.BasePermission):
    """Permission for teachers and admins."""
    
    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            (request.user.is_staff or hasattr(request.user, 'teacher_profile'))
        )


class IsOwnerOrTeacher(permissions.BasePermission):
    """Permission for object owner or teacher."""
    
    def has_object_permission(self, request, view, obj):
        # Admins can access everything
        if request.user.is_staff:
            return True
        
        # Teachers can access their students' data
        if hasattr(request.user, 'teacher_profile'):
            # Check if student is in teacher's class (implement based on your model)
            return True
        
        # Students can only access their own data
        if hasattr(obj, 'student'):
            return obj.student == request.user
        if hasattr(obj, 'user'):
            return obj.user == request.user
        
        return False