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


def enroll_student(domain: EnrollmentDomain) -> EnrollmentDomain:
    """
    Direct enroll (teacher/admin adds student).
    Domain must contain classroom_id and student_id.
    """
    call_validate(domain)
    # check classroom
    try:
        cls = ClassroomModel.objects.get(pk=domain.classroom_id)
    except ClassroomModel.DoesNotExist:
        raise NotFoundError("Classroom not found")

    if cls.status != "active":
        raise InvalidOperation("Cannot enroll into non-active classroom")

    # create or get existing
    try:
        with transaction.atomic():
            enroll, created = Enrollment.objects.get_or_create(
                classroom_id=domain.classroom_id,
                student_id=domain.student_id,
                defaults={"role": domain.role or "student", "status": EnrollmentDomain.STATUS_ACTIVE}
            )
    except IntegrityError as e:
        # handle race condition
        enroll = Enrollment.objects.filter(classroom_id=domain.classroom_id, student_id=domain.student_id).first()
        if not enroll:
            raise

    return EnrollmentDomain.from_model(enroll)


def drop_enrollment(domain: EnrollmentDomain) -> EnrollmentDomain:
    """
    Drop enrollment (student leaves or teacher drops).
    """
    if not domain.classroom_id or not domain.student_id:
        raise DomainValidationError("classroom_id and student_id are required")
    try:
        enroll = Enrollment.objects.get(classroom_id=domain.classroom_id, student_id=domain.student_id)
    except Enrollment.DoesNotExist:
        raise NotFoundError("Enrollment not found")
    enroll.status = EnrollmentDomain.STATUS_DROPPED
    enroll.save()

    # also mark membership inactive if exists
    MembershipModel.objects.filter(classroom_id=domain.classroom_id, student_id=domain.student_id).update(is_active=False)
    return EnrollmentDomain.from_model(enroll)