# import uuid
# from uuid import uuid4
# from typing import Optional
# from django.db import transaction
# from datetime import timedelta, timezone

# from account.models import UserModel
# from school.models import ClassroomModel, MembershipModel, InvitationModel
# from school.domains.class_domain import MembershipDomain, ClassroomDomain
# from school.domains.invitation_domain import InvitationDomain
# from school.api.permissions import PermissionDenied, ConflictError, NotFoundError, InvalidOperation, ensure_is_admin_or_instructor
# from backend.school.services.membership_service import join_classroom


# @transaction.atomic
# def create_invitation(
#     requesting: UserModel,
#     classroom_id: int,
#     email: str,
#     expire_days: int = 7,
#     usage_limit: Optional[int] = None,
# ) -> InvitationDomain:
#     """
#     Create an invitation for a classroom.
#     - Generates unique invite_code (UUID4).
#     - Restrict by email (unique).
#     - Set expiration and usage limit.
#     - Initial status = "pending".
#     """
#     try:
#         classroom_model = ClassroomModel.objects.get(id=classroom_id)
#     except ClassroomModel.DoesNotExist:
#         raise NotFoundError("Classroom not found.")

#     ensure_is_admin_or_instructor(requesting, classroom_model)

#     # Generate invite code (UUID4 → string)
#     invite_code = str(uuid.uuid4())

#     invitation_model = InvitationModel.objects.create(
#         classroom=classroom_model,
#         invite_code=invite_code,
#         email=email,
#         created_by=requesting.id,
#         expires_on=timezone.now() + timedelta(days=expire_days),
#         status="pending",
#         usgaed_limit=usage_limit,
#         used_count=0,
#     )

#     return InvitationDomain.from_model(invitation_model)


# def get_invitation(*, invite_code: str = None, invitation_id: int = None) -> Optional[InvitationDomain]:
#     """Fetch invitation by code or id."""
#     try:
#         if invite_code:
#             model = InvitationModel.objects.get(invite_code=invite_code)
#         elif invitation_id:
#             model = InvitationModel.objects.get(id=invitation_id)
#         else:
#             return None
#         return InvitationDomain.from_model(model)
#     except InvitationModel.DoesNotExist:
#         return None
    

# def validate_invitation(invite_code: str) -> InvitationDomain:
#     """
#     Validate invitation: must be active, not expired, not over usage_limit.
#     Raises InvalidOperation if invalid.
#     """
#     try:
#         invitation_model = InvitationModel.objects.get(invite_code=invite_code)
#     except InvitationModel.DoesNotExist:
#         raise NotFoundError("Invitation not found.")

#     invitation_domain = InvitationDomain.from_model(invitation_model)

#     if not invitation_domain.is_valid():
#         invitation_model.status = "expired"
#         invitation_model.save(update_fields=["status"])
#         raise InvalidOperation("Invitation is not valid or has expired.")

#     return invitation_domain


# @transaction.atomic
# def accept_invitation(student: UserModel, invite_code: str) -> MembershipDomain:
#     """
#     Accept an invitation by invite_code. Creates membership and updates invitation usage/status.
#     """
#     try:
#         invitation_model = InvitationModel.objects.select_for_update().get(invite_code=invite_code)
#     except InvitationModel.DoesNotExist:
#         raise NotFoundError("Invitation not found.")
#     invitation_domain = InvitationDomain.from_model(invitation_model)

#     # Check classroom status
#     try:
#         classroom_model = invitation_model.classroom
#     except Exception:
#         raise NotFoundError("Classroom for invitation not found.")
#     classroom_domain = ClassroomDomain.from_model(classroom_model)
#     classroom_domain.ensure_active()

#     invitation_domain.mark_used()
#     invitation_domain.save()

#     return join_classroom(student, classroom_model.id, invite_code)


# @transaction.atomic
# def revoke_invitation(requesting: UserModel, invitation_id: int) -> InvitationDomain:
#     """
#     Revoke (cancel) an invitation.
#     Only admin/instructor allowed.
#     """
#     try:
#         invitation_model = InvitationModel.objects.select_for_update().get(id=invitation_id)
#     except InvitationModel.DoesNotExist:
#         raise NotFoundError("Invitation not found.")

#     ensure_is_admin_or_instructor(requesting, invitation_model.classroom)

#     if invitation_model.status != "active":
#         raise InvalidOperation("Only active invitations can be revoked.")

#     invitation_model.status = "revoked"
#     invitation_model.save(update_fields=["status"])
#     return InvitationDomain.from_model(invitation_model)


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


def invite_student(domain: InvitationDomain) -> InvitationDomain:
    """
    Create an invitation (single use or multi-use).
    - domain.classroom_id, domain.email, domain.created_by, domain.usage_limit expected
    """
    call_validate(domain)

    # validate classroom exists and is active
    try:
        classroom = ClassroomModel.objects.get(pk=domain.classroom_id)
    except ClassroomModel.DoesNotExist:
        raise NotFoundError("Classroom not found")

    if classroom.status != "active":
        raise InvalidOperation("Cannot invite students to non-active classroom")

    # create InvitationModel
    code = getattr(domain, "invite_code", None) or str(uuid.uuid4())
    expires_on = getattr(domain, "expires_on", None)
    if not expires_on:
        # default expiration: 7 days from now (or domain may specify different)
        expires_on = timezone.now() + timedelta(days=getattr(domain, "days_valid", 7))

    # Note: original model field name has typo 'usgaed_limit' so set both to be safe
    inv = InvitationModel.objects.create(
        classroom_id=domain.classroom_id,
        invite_code=code,
        email=domain.email,
        created_by=domain.created_by,
        created_on=getattr(domain, "created_on", timezone.now()),
        expires_on=expires_on,
        status=domain.status or InvitationDomain.STATUS_PENDING,
        # tolerate either attribute name
        usgaed_limit=getattr(domain, "usage_limit", None),
        used_count=getattr(domain, "used_count", 0),
    )
    return InvitationDomain.from_model(inv)


def invite_students_bulk(domains: Iterable[InvitationDomain]) -> List[InvitationDomain]:
    """
    Bulk invite. This function will try to create invitations in a single transaction.
    Returns created InvitationDomain list.
    """
    created = []
    with transaction.atomic():
        for dom in domains:
            call_validate(dom)
            created.append(invite_student(dom))
    return created


def revoke_invitation_by_code(invite_code: str) -> InvitationDomain:
    """Mark invitation expired/revoked."""
    try:
        inv = InvitationModel.objects.get(invite_code=invite_code)
    except InvitationModel.DoesNotExist:
        raise NotFoundError("Invitation not found")

    inv.status = InvitationDomain.STATUS_EXPIRED
    inv.save()
    return InvitationDomain.from_model(inv)


def resend_invitation(invite_code: str, send_email_fn=None) -> InvitationDomain:
    """
    Optionally triggers sending email via send_email_fn(invitation_model) if provided.
    Does not alter invite_code but updates updated timestamp.
    """
    try:
        inv = InvitationModel.objects.get(invite_code=invite_code)
    except InvitationModel.DoesNotExist:
        raise NotFoundError("Invitation not found")

    if inv.status != InvitationDomain.STATUS_PENDING:
        raise InvalidOperation("Only pending invitations can be resent")

    inv.created_on = timezone.now()  # or track a separate 'last_sent' field
    inv.save()

    if send_email_fn:
        try:
            send_email_fn(inv)
        except Exception as e:
            logger.exception("Failed to resend invitation email: %s", e)

    return InvitationDomain.from_model(inv)


# -------------------------
# Accept invitation -> creates enrollment + membership
# -------------------------
def accept_invitation(invitation_domain: InvitationDomain, student_id: Any) -> EnrollmentDomain:
    """
    Student accepts invitation by code.
    Steps (atomic):
      - lock invitation row (select_for_update)
      - check invitation.can_be_used(); update used_count/status
      - ensure classroom is active
      - create or get Enrollment
      - create or ensure Membership
    Returns EnrollmentDomain (created or existing).
    """
    if not getattr(invitation_domain, "invite_code", None):
        raise DomainValidationError("invite_code required")

    with transaction.atomic():
        try:
            inv_row = InvitationModel.objects.select_for_update().get(invite_code=invitation_domain.invite_code)
        except InvitationModel.DoesNotExist:
            raise NotFoundError("Invitation not found")

        # map to domain from DB to get canonical data (including server-side used_count)
        inv_dom = InvitationDomain.from_model(inv_row)

        # Check usable
        if not inv_dom.can_be_used(now=timezone.now()):
            raise InvalidOperation("Invitation cannot be used")

        # Accept in domain (will update used_count/status)
        try:
            inv_dom.accept(now=timezone.now())
        except Exception as e:
            raise InvalidOperation(str(e))

        # persist invitation changes
        inv_row.used_count = inv_dom.used_count
        inv_row.status = inv_dom.status
        inv_row.save()

        # ensure classroom exists and is active
        try:
            cls_row = ClassroomModel.objects.select_for_update().get(pk=inv_dom.classroom_id)
        except ClassroomModel.DoesNotExist:
            raise NotFoundError("Classroom not found")

        if cls_row.status != "active":
            raise InvalidOperation("Classroom not accepting new members")

        # Create or get Enrollment
        enrollment_obj, created = Enrollment.objects.get_or_create(
            classroom_id=inv_dom.classroom_id,
            student_id=student_id,
            defaults={"role": "student", "status": EnrollmentDomain.STATUS_ACTIVE}
        )

        # Create membership if not exists
        membership_qs = MembershipModel.objects.filter(classroom_id=inv_dom.classroom_id, student_id=student_id)
        if not membership_qs.exists():
            MembershipModel.objects.create(
                classroom_id=inv_dom.classroom_id,
                student_id=student_id,
                role="student",
                joined_on=timezone.now(),
                is_active=True,
            )

        return EnrollmentDomain.from_model(enrollment_obj)


def validate_invite_code(invite_code: str) -> InvitationDomain:
    """Simple read-only validation of invite code."""
    try:
        inv = InvitationModel.objects.get(invite_code=invite_code)
    except InvitationModel.DoesNotExist:
        raise NotFoundError("Invitation not found")

    inv_dom = InvitationDomain.from_model(inv)
    if not inv_dom.can_be_used(now=timezone.now()):
        raise InvalidOperation("Invitation not valid")
    return inv_dom