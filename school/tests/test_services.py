# school/tests/test_services.py
import pytest
from django.utils import timezone
from datetime import timedelta

from school.domains.school_domain import SchoolDomain
from school.domains.class_domain import ClassroomDomain
from school.domains.invitation_domain import InvitationDomain
from school.domains.enrollment_domain import EnrollmentDomain
from school.domains.membership_domain import MembershipDomain

from school.services.class_services import (
    create_classroom,
    list_classrooms_by_school,
)
from school.services.school_service import create_school, get_school
from school.services.invitation_service import invite_student, accept_invitation, revoke_invitation_by_code
from school.services.enrollment_service import enroll_student, drop_enrollment
from school.services.membership_service import add_member, list_members
from school.services.exceptions import DuplicateError, NotFoundError, InvalidOperation, DomainValidationError



@pytest.mark.django_db
def test_create_and_get_school():
    dom = SchoolDomain(id=None, name="S1", code="C1", metadata={"city": "H"})
    created = create_school(dom)
    assert created.id is not None
    loaded = get_school(created.id)
    assert loaded.name == "S1"

@pytest.mark.django_db
def test_create_classroom_and_duplicate(school_factory, user_factory):
    school = school_factory(name="SCX")
    teacher = user_factory(username="teachX")
    dom = ClassroomDomain(id=None, class_name="A1", created_by=teacher.id, status="active")
    # attach school id
    dom.school = school.id
    created = create_classroom(dom)
    assert created.class_name == "A1"

    # duplicate within same school should raise DuplicateError
    with pytest.raises(DuplicateError):
        create_classroom(dom)


@pytest.mark.django_db
def test_invite_student_and_accept_flow(classroom_factory, user_factory):
    teacher = user_factory(username="teachI")
    classroom = classroom_factory(teacher=teacher, created_by=teacher.id)
    student = user_factory(username="studI")
    now = timezone.now()
    inv_dom = InvitationDomain(
        id=None,
        classroom_id=classroom.id,
        invite_code=None,
        email=student.email,
        created_by=teacher.id,
        created_on=now,
        expires_on=now + timedelta(days=5),
        status=InvitationDomain.STATUS_PENDING,
        usage_limit=1,
        used_count=0
    )
    created_inv = invite_student(inv_dom)
    assert created_inv.invite_code is not None

    # student accepts
    enrollment = accept_invitation(created_inv, student.id)
    assert enrollment.classroom_id == classroom.id
    assert enrollment.student_id == student.id


@pytest.mark.django_db
def test_invite_to_archived_classroom_not_allowed(classroom_factory, user_factory):
    teacher = user_factory(username="tarch")
    classroom = classroom_factory(teacher=teacher, created_by=teacher.id, status="archived")
    now = timezone.now()
    inv_dom = InvitationDomain(
        id=None,
        classroom_id=classroom.id,
        invite_code=None,
        email="x@y.com",
        created_by=teacher.id,
        created_on=now,
        expires_on=now + timedelta(days=2),
        status=InvitationDomain.STATUS_PENDING,
        usage_limit=1,
        used_count=0
    )
    with pytest.raises(InvalidOperation):
        invite_student(inv_dom)


@pytest.mark.django_db
def test_direct_enroll_and_drop(classroom_factory, user_factory):
    teacher = user_factory(username="tEn")
    classroom = classroom_factory(teacher=teacher, created_by=teacher.id)
    student = user_factory(username="sEn")

    enroll_dom = EnrollmentDomain(id=None, classroom_id=classroom.id, student_id=student.id, role="student")
    created = enroll_student(enroll_dom)
    assert created.classroom_id == classroom.id
    # drop
    drop_dom = EnrollmentDomain(id=None, classroom_id=classroom.id, student_id=student.id, role="student")
    dropped = drop_enrollment(drop_dom)
    assert dropped.status == EnrollmentDomain.STATUS_DROPPED


@pytest.mark.django_db
def test_add_member_and_list(classroom_factory, user_factory):
    teacher = user_factory(username="mT")
    classroom = classroom_factory(teacher=teacher, created_by=teacher.id)
    student = user_factory(username="mS")
    dom = MembershipDomain(classroom_id=classroom.id, student_id=student.id, role="student")
    m = add_member(dom)
    assert m.role == "student"
    members = list_members(classroom.id)
    assert any(x.student_id == student.id for x in members)


@pytest.mark.django_db
def test_revoke_invitation(invitation_factory):
    inv = invitation_factory()
    # call revoke by code
    revoked = revoke_invitation_by_code(inv.invite_code)
    assert revoked.status == InvitationDomain.STATUS_EXPIRED
