# school/tests/test_domain.py
import pytest
from datetime import timedelta
from django.utils import timezone

from school.domains.class_domain import ClassroomDomain
from school.domains.invitation_domain import InvitationDomain
from school.domains.enrollment_domain import EnrollmentDomain
from school.domains.membership_domain import MembershipDomain
from school.services.exceptions import DomainValidationError, InvalidOperation

@pytest.mark.unit
def test_classroom_domain_archive_and_activate():
    dom = ClassroomDomain(id=None, class_name="C1", created_by=1, status="active")
    assert dom.can_accept_new_members() is True
    dom.archive()
    assert dom.status == "archived"
    assert dom.can_accept_new_members() is False
    dom.activate()
    assert dom.status == "active"

@pytest.mark.unit
def test_classroom_require_name_validation():
    with pytest.raises(DomainValidationError):
        ClassroomDomain(id=None, class_name="", created_by=1)

@pytest.mark.unit
def test_membership_domain_validation_ok_and_bad_role():
    # valid roles should pass
    MembershipDomain(classroom_id=1, student_id=1, role="student")
    MembershipDomain(classroom_id=1, student_id=2, role="instructor")
    # invalid role must raise
    with pytest.raises(DomainValidationError):
        MembershipDomain(classroom_id=1, student_id=1, role="notarole")

@pytest.mark.unit
def test_enrollment_drop_behavior():
    e = EnrollmentDomain(id=None, classroom_id=1, student_id=1, role="student", status=EnrollmentDomain.STATUS_ACTIVE)
    e.drop()
    assert e.status == EnrollmentDomain.STATUS_DROPPED
    with pytest.raises(ValueError):
        # dropping again should error (only drop active)
        e.drop()

@pytest.mark.unit
def test_invitation_can_be_used_and_accept_flow():
    now = timezone.now()
    inv = InvitationDomain(
        id=None,
        classroom_id=1,
        invite_code="code1",
        email="a@b.com",
        created_by=1,
        created_on=now,
        expires_on=now + timedelta(days=2),
        status=InvitationDomain.STATUS_PENDING,
        usage_limit=2,
        used_count=0
    )
    assert inv.can_be_used() is True
    inv.accept(now=now)
    assert inv.used_count == 1
    # still can be used (usage_limit 2)
    assert inv.can_be_used() is True
    inv.accept(now=now)
    # used up -> status becomes accepted
    assert inv.used_count == 2
    assert inv.status == InvitationDomain.STATUS_ACCEPTED

@pytest.mark.unit
def test_invitation_expired():
    now = timezone.now()
    inv = InvitationDomain(
        id=None,
        classroom_id=1,
        invite_code="code2",
        email="c@d.com",
        created_by=1,
        created_on=now - timedelta(days=10),
        expires_on=now - timedelta(days=1),
        status=InvitationDomain.STATUS_PENDING,
        usage_limit=1,
        used_count=0
    )
    assert inv.is_expired(now=now) is True
    assert inv.can_be_used(now=now) is False
    with pytest.raises(InvalidOperation):
        inv.accept(now=now)
