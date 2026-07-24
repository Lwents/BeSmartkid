# api/v1/permissions.py
"""Custom permissions for Assignment API."""
from rest_framework import permissions


class IsTeacher(permissions.BasePermission):
    """Permission: User must be a teacher."""
    
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and \
               hasattr(request.user, 'role') and request.user.role in ['teacher', 'instructor']


class IsStudent(permissions.BasePermission):
    """Permission: User must be a student."""
    
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and \
               hasattr(request.user, 'role') and request.user.role == 'student'


class IsAssignmentOwner(permissions.BasePermission):
    """Permission: User must be assignment creator."""
    
    def has_object_permission(self, request, view, obj):
        return obj.teacher_id == request.user.id


class IsSubmissionOwner(permissions.BasePermission):
    """Permission: User must be submission owner."""
    
    def has_object_permission(self, request, view, obj):
        return obj.student_id == request.user.id


class CanGrade(permissions.BasePermission):
    """Permission: User can grade (teacher of the assignment)."""
    
    def has_object_permission(self, request, view, obj):
        # obj is submission, check if user is teacher of assignment
        return hasattr(request.user, 'role') and \
               request.user.role in ['teacher', 'instructor']
