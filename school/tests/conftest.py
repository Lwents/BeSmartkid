# school/tests/conftest.py
import uuid
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

from school.models import SchoolModel, ClassroomModel, InvitationModel, MembershipModel, Enrollment

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user_factory(db):
    def create_user(username="user", email=None, password="password", **kwargs):
        email = email or f"{username}@example.com"
        user = User.objects.create_user(username=username, email=email, password=password, **kwargs)
        return user
    return create_user


@pytest.fixture
def school_factory(db):
    def create_school(name="Test School", code=None, metadata=None):
        code = code or f"SC-{uuid.uuid4().hex[:6]}"
        return SchoolModel.objects.create(name=name, code=code, metadata=metadata or {})
    return create_school


@pytest.fixture
def classroom_factory(db, user_factory, school_factory):
    def create_classroom(school=None, class_name="1A", grade="1", teacher=None, created_by=None, status="active"):
        if school is None:
            school = school_factory()
        if teacher is None:
            teacher = user_factory(username="teacher_" + uuid.uuid4().hex[:4])
        if created_by is None:
            created_by = teacher.id
        # Try to set teacher field; classroom model might expect FK to auth.User or UserModel
        return ClassroomModel.objects.create(
            school=school,
            class_name=class_name,
            grade=grade,
            teacher=teacher,
            created_by=created_by,
            status=status
        )
    return create_classroom


@pytest.fixture
def invitation_factory(db, classroom_factory, user_factory):
    def create_invite(classroom=None, email=None, created_by=None, days_valid=7, usage_limit=1, status="pending"):
        if classroom is None:
            classroom = classroom_factory()
        if created_by is None:
            created_by = classroom.created_by
        email = email or f"inv-{uuid.uuid4().hex[:6]}@example.com"
        now = timezone.now()
        inv = InvitationModel.objects.create(
            classroom=classroom,
            invite_code=str(uuid.uuid4()),
            email=email,
            created_by=created_by,
            created_on=now,
            expires_on=now + timedelta(days=days_valid),
            status=status,
            usgaed_limit=usage_limit,
            used_count=0
        )
        return inv
    return create_invite


@pytest.fixture
def membership_factory(db, classroom_factory, user_factory):
    def create_membership(classroom=None, student=None, role="student", is_active=True):
        if classroom is None:
            classroom = classroom_factory()
        if student is None:
            student = user_factory(username="std_" + uuid.uuid4().hex[:4])
        return MembershipModel.objects.create(
            classroom=classroom,
            student=student,
            role=role,
            is_active=is_active
        )
    return create_membership


@pytest.fixture
def enrollment_factory(db, classroom_factory, user_factory):
    def create_enrollment(classroom=None, student=None, role="student", status="active"):
        if classroom is None:
            classroom = classroom_factory()
        if student is None:
            student = user_factory(username="stdE_" + uuid.uuid4().hex[:4])
        return Enrollment.objects.create(
            classroom=classroom,
            student=student,
            role=role,
            status=status
        )
    return create_enrollment


# school/tests/conftest.py
import pytest
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from custom_account.tests.factories import UserFactory
from school.tests.factories import (
    SchoolFactory, ClassroomFactory, EnrollmentFactory,
    TeacherAssignmentFactory, SchoolYearFactory
)

@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture
def school_factory(db):
    return SchoolFactory

@pytest.fixture
def classroom_factory(db):
    return ClassroomFactory

@pytest.fixture
def enrollment_factory(db):
    return EnrollmentFactory

@pytest.fixture
def teacher_assignment_factory(db):
    return TeacherAssignmentFactory

@pytest.fixture
def school_year_factory(db):
    return SchoolYearFactory

# Authenticated clients with different roles
@pytest.fixture
def student_auth_client(db, api_client):
    student = UserFactory(role="student")
    token, _ = Token.objects.get_or_create(user=student)
    api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return api_client, student, token

@pytest.fixture
def teacher_auth_client(db, api_client):
    teacher = UserFactory(role="teacher")
    token, _ = Token.objects.get_or_create(user=teacher)
    api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return api_client, teacher, token

@pytest.fixture
def principal_auth_client(db, api_client):
    principal = UserFactory(role="principal", is_staff=True)
    token, _ = Token.objects.get_or_create(user=principal)
    api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return api_client, principal, token

