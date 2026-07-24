"""
Classroom service wrapper for API views
"""
from typing import List, Any
from school.services.class_services import (
    create_classroom as _create_classroom,
    get_classroom as _get_classroom,
    update_classroom as _update_classroom,
    archive_classroom as _archive_classroom,
    list_classrooms_by_school,
)
from school.domains.class_domain import ClassroomDomain
from school.models import ClassroomModel
from custom_account.models import UserModel


def list_classrooms(user: UserModel = None) -> List[ClassroomDomain]:
    """
    List classrooms. If user is provided and is instructor, filter to their classrooms.
    """
    if user and hasattr(user, 'role') and user.role == 'instructor' and not user.is_staff:
        # Filter to classrooms where user is the teacher
        classrooms = ClassroomModel.objects.filter(teacher=user)
        return [ClassroomDomain.from_model(c) for c in classrooms]
    
    # For admins or no user, return all active classrooms
    classrooms = ClassroomModel.objects.exclude(status__in=['archived', 'deleted'])
    return [ClassroomDomain.from_model(c) for c in classrooms]


def create_classroom(domain: ClassroomDomain) -> ClassroomDomain:
    """Create classroom"""
    return _create_classroom(domain)


def get_classroom(classroom_id: Any) -> ClassroomDomain:
    """Get classroom by ID"""
    return _get_classroom(classroom_id)


def update_classroom(domain: ClassroomDomain) -> ClassroomDomain:
    """Update classroom"""
    return _update_classroom(domain)


def archive_classroom(classroom_id: Any) -> None:
    """Archive classroom"""
    classroom = _get_classroom(classroom_id)
    domain = ClassroomDomain.from_model(ClassroomModel.objects.get(pk=classroom_id))
    _archive_classroom(domain)




