# from typing import Optional
# from django.db import transaction

# from account.models import UserModel
# from school.models import ClassroomModel, MembershipModel
# from school.domains.class_domain import ClassroomDomain
# from school.services.exceptions import PermissionDenied, ConflictError, NotFoundError, InvalidOperation
# from school.services.validators import ensure_is_admin_or_instructor, ensure_is_admin



# @transaction.atomic
# def create_classroom(instructor: UserModel, name: str, description: Optional[str] = None) -> ClassroomDomain:
#     """Create a classroom and add instructor as member."""
#     # Basic permission: only instructor/admin can create class (you can relax this if needed)
#     if not (instructor.is_staff or instructor.role == "instructor"):
#         raise PermissionDenied("Only instructors or admins can create a classroom.")

#     # Ensure unique name (class_name)
#     if ClassroomModel.objects.filter(class_name__iexact=name).exists():
#         raise ConflictError(f"Classroom with name '{name}' already exists.")

#     classroom_model = ClassroomModel.objects.create(
#         class_name=name,
#         created_by=instructor.id,
#         status="active",
#     )

#     # create membership
#     MembershipModel.objects.create(
#         classroom=classroom_model,
#         student=instructor,
#         role="instructor",
#     )

#     return ClassroomDomain.from_model(classroom_model)


# @transaction.atomic
# def archive_classroom(requesting: UserModel, classroom_id: int) -> ClassroomDomain:
#     """
#     Archive the classroom (soft-close). Only instructor or admin can archive.
#     """
#     try:
#         classroom_model = ClassroomModel.objects.select_for_update().get(id=classroom_id)
#     except ClassroomModel.DoesNotExist:
#         raise NotFoundError("Classroom not found.")

#     ensure_is_admin_or_instructor(requesting, classroom_model)

#     if classroom_model.status != "active":
#         raise InvalidOperation("Only active classrooms can be archived.")

#     classroom_model.status = "archived"
#     classroom_model.save(update_fields=["status", "updated_on"])

#     return ClassroomDomain.from_model(classroom_model)


# @transaction.atomic
# def restore_classroom(requesting: UserModel, classroom_id: int) -> ClassroomDomain:
#     """
#     Restore an archived classroom to active. Only admin or instructor allowed.
#     """
#     try:
#         classroom_model = ClassroomModel.objects.select_for_update().get(id=classroom_id)
#     except ClassroomModel.DoesNotExist:
#         raise NotFoundError("Classroom not found.")
    
#     ensure_is_admin_or_instructor(requesting, ClassroomModel)

#     if classroom_model.status != "archived":
#         raise InvalidOperation("Only archived classrooms can be restored.")
#     classroom_model.status = "active"
#     classroom_model.save(update_fields=["status", "updated_on"])
#     return ClassroomDomain.from_model(classroom_model)


# @transaction.atomic
# def update_classroom(requesting: UserModel, classroom_id: int, *, name: Optional[str] = None,
#                      description: Optional[str] = None) -> ClassroomDomain:
#     """
#     Update classroom metadata. Only instructor/admin allowed.
#     """
#     try:
#         classroom_model = ClassroomModel.objects.select_for_update().get(id=classroom_id)
#     except ClassroomModel.DoesNotExist:
#         raise NotFoundError("Classroom not found.")

#     ensure_is_admin_or_instructor(requesting, classroom_model)

#     if name:
#         # ensure uniqueness of name
#         if ClassroomModel.objects.filter(class_name__iexact=name).exclude(id=classroom_id).exists():
#             raise ConflictError("Another classroom with this name already exists.")
#         classroom_model.class_name = name
#     if description is not None:
#         # optional field; set even if empty string
#         classroom_model.description = description

#     classroom_model.save()
#     return ClassroomDomain.from_model(classroom_model)


# @transaction.atomic
# def delete_classroom(requesting: UserModel, classroom_id: int, *, soft_delete: bool = True) -> None:
#     """
#     Delete classroom. Default is soft-delete (set status='deleted').
#     Only admin can hard-delete. Instructors may soft-delete if permitted.
#     Returns None.
#     """
#     try:
#         classroom_model = ClassroomModel.objects.select_for_update().get(id=classroom_id)
#     except ClassroomModel.DoesNotExist:
#         raise NotFoundError("Classroom not found.")

#     if soft_delete:
#         ensure_is_admin_or_instructor(requesting, classroom_model)
#         classroom_model.status = "deleted"
#         classroom_model.save(update_fields=["status", "updated_on"])
#         return

#     # hard delete
#     ensure_is_admin(requesting)
#     classroom_model.delete()
# #     return


from typing import List, Optional, Any, Iterable
from datetime import datetime, timedelta
import uuid
import csv
import io
import logging

from django.db import transaction, IntegrityError
from django.utils import timezone
from django.core.exceptions import ObjectDoesNotExist

from school.models import (
    SchoolModel,
    ClassroomModel,
    MembershipModel,
    Enrollment,
    InvitationModel,
)
from school.domains.school_domain import SchoolDomain
from school.domains.class_domain import ClassroomDomain
from school.domains.membership_domain import MembershipDomain
from school.domains.enrollment_domain import EnrollmentDomain
from school.domains.invitation_domain import InvitationDomain
from school.services.exceptions import NotFoundError, InvalidOperation, DuplicateError, DomainValidationError

logger = logging.getLogger(__name__)


# -------------------------
# Helper utilities
# -------------------------
def call_validate(domain_obj):
    """Call 'validate' if exists else '_validate' to keep compatibility with different domain naming."""
    if domain_obj is None:
        return
    if hasattr(domain_obj, "validate"):
        return domain_obj.validate()
    if hasattr(domain_obj, "_validate"):
        return domain_obj._validate()
    return None



def create_classroom(domain: ClassroomDomain) -> ClassroomDomain:
    """
    Create classroom from domain.
    - domain.created_by expected
    - domain.class_name required
    """
    call_validate(domain)

    # Optional: ensure school exists if domain has school id attribute
    if getattr(domain, "school", None):
        try:
            SchoolModel.objects.get(pk=domain.school)
        except SchoolModel.DoesNotExist:
            raise NotFoundError("School not found")

    # unique constraint on class_name if you require global uniqueness; otherwise scoped to school
    # We'll assume class_name unique within school -> check if same school/class_name exists
    filters = {"class_name": domain.class_name}
    if getattr(domain, "school", None):
        filters["school_id"] = domain.school

    if ClassroomModel.objects.filter(**filters).exists():
        raise DuplicateError("Classroom with same name already exists in this school")

    cls = ClassroomModel.objects.create(
        school_id=getattr(domain, "school", None),
        class_name=domain.class_name,
        grade=getattr(domain, "grade", None),
        teacher_id=getattr(domain, "teacher", None),
        created_by=domain.created_by,
        status=domain.status or "active",
    )
    return ClassroomDomain.from_model(cls)


def get_classroom(classroom_id: Any) -> ClassroomDomain:
    try:
        cls = ClassroomModel.objects.get(pk=classroom_id)
    except ClassroomModel.DoesNotExist:
        raise NotFoundError("Classroom not found")
    return ClassroomDomain.from_model(cls)


def list_classrooms_by_school(school_id: Any, include_archived: bool = False) -> List[ClassroomDomain]:
    qs = ClassroomModel.objects.filter(school_id=school_id)
    if not include_archived:
        qs = qs.exclude(status__in=["archived", "deleted"])
    return [ClassroomDomain.from_model(c) for c in qs.order_by("class_name")]


def update_classroom(domain: ClassroomDomain) -> ClassroomDomain:
    """
    Update classroom from domain. domain.id must exist.
    """
    if not domain.id:
        raise DomainValidationError("Classroom ID is required to update")
    call_validate(domain)

    try:
        cls = ClassroomModel.objects.get(pk=domain.id)
    except ClassroomModel.DoesNotExist:
        raise NotFoundError("Classroom not found")

    # apply permitted updates (business rules in domain should also be applied earlier)
    cls.class_name = domain.class_name
    cls.grade = getattr(domain, "grade", cls.grade)
    cls.teacher_id = getattr(domain, "teacher", cls.teacher_id)
    cls.status = domain.status
    # allow metadata if present on domain
    if hasattr(domain, "metadata"):
        setattr(cls, "metadata", getattr(domain, "metadata", {}) or {})
    cls.save()
    return ClassroomDomain.from_model(cls)


def archive_classroom(domain: ClassroomDomain) -> ClassroomDomain:
    """
    Archive classroom. domain.id required.
    """
    if not domain.id:
        raise DomainValidationError("Classroom ID required")
    # domain.ensure_active()  # domain rule
    call_validate(domain)

    try:
        cls = ClassroomModel.objects.get(pk=domain.id)
    except ClassroomModel.DoesNotExist:
        raise NotFoundError("Classroom not found")

    domain.archive()
    cls.status = domain.status
    cls.save()
    return ClassroomDomain.from_model(cls)


def restore_classroom(domain: ClassroomDomain) -> ClassroomDomain:
    """
    Restore archived classroom to active.
    """
    if not domain.id:
        raise DomainValidationError("Classroom ID required")
    try:
        cls = ClassroomModel.objects.get(pk=domain.id)
    except ClassroomModel.DoesNotExist:
        raise NotFoundError("Classroom not found")

    domain.activate()
    cls.status = domain.status
    cls.save()
    return ClassroomDomain.from_model(cls)


def delete_classroom(domain: ClassroomDomain, hard_delete: bool = False) -> None:
    """
    Delete classroom. If hard_delete True -> DB delete, else mark deleted (domain.delete()).
    """
    if not domain.id:
        raise DomainValidationError("Classroom ID required")
    try:
        cls = ClassroomModel.objects.get(pk=domain.id)
    except ClassroomModel.DoesNotExist:
        raise NotFoundError("Classroom not found")

    if hard_delete:
        # caution: cascade to enrollments, memberships, invitations
        cls.delete()
        return

    domain.delete()
    cls.status = domain.status
    cls.save()
    return
