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



def create_school(domain: SchoolDomain) -> SchoolDomain:
    """
    Create a new school from domain.
    - domain: SchoolDomain (id may be None)
    """
    call_validate(domain)
    # simple uniqueness check for code if provided
    if domain.code:
        if SchoolModel.objects.filter(code=domain.code).exists():
            raise DuplicateError("School code already used")

    school = SchoolModel.objects.create(
        name=domain.name,
        code=domain.code,
        metadata=domain.metadata or {},
    )
    return SchoolDomain.from_model(school)


def get_school(school_id: Any) -> SchoolDomain:
    try:
        s = SchoolModel.objects.get(pk=school_id)
    except SchoolModel.DoesNotExist:
        raise NotFoundError("School not found")
    return SchoolDomain.from_model(s)


def update_school(domain: SchoolDomain) -> SchoolDomain:
    """
    Update existing school: domain.id must be set.
    """
    if not domain.id:
        raise DomainValidationError("School ID is required for update")
    call_validate(domain)

    try:
        s = SchoolModel.objects.get(pk=domain.id)
    except SchoolModel.DoesNotExist:
        raise NotFoundError("School not found")

    # update fields
    s.name = domain.name
    s.code = domain.code
    s.metadata = domain.metadata or {}
    s.save()
    return SchoolDomain.from_model(s)


def list_schools() -> List[SchoolDomain]:
    return [SchoolDomain.from_model(s) for s in SchoolModel.objects.all()]


def delete_school(school_id: Any, hard_delete: bool = False) -> None:
    """
    Delete a school. By default soft-delete via metadata flag; set hard_delete to True to remove DB row.
    """
    try:
        s = SchoolModel.objects.get(pk=school_id)
    except SchoolModel.DoesNotExist:
        raise NotFoundError("School not found")

    if hard_delete:
        s.delete()
        return
    meta = s.metadata or {}
    meta["deleted"] = True
    s.metadata = meta
    s.save()
    return