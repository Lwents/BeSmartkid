# tests/conftest.py
"""Pytest configuration and fixtures."""
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4
from unittest.mock import Mock

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from assignments.models import (
    Assignment,
    Submission,
    Grade
)

User = get_user_model()


@pytest.fixture
def api_client():
    """DRF API client."""
    return APIClient()


@pytest.fixture
def teacher_user(db):
    """Create teacher user."""
    user = User.objects.create_user(
        username='teacher1',
        email='teacher@test.com',
        password='testpass123'
    )
    user.role = 'teacher'
    user.save()
    return user


@pytest.fixture
def student_user(db):
    """Create student user."""
    user = User.objects.create_user(
        username='student1',
        email='student@test.com',
        password='testpass123'
    )
    user.role = 'student'
    user.save()
    return user


@pytest.fixture
def classroom(db):
    """Create classroom mock."""
    from unittest.mock import Mock
    classroom = Mock()
    classroom.id = uuid4()
    return classroom


@pytest.fixture
def assignment_model(db, teacher_user, classroom):
    """Create assignment model."""
    return Assignment.objects.create(
        id=uuid4(),
        title="Test Assignment",
        description="Test Description",
        assignment_type='homework',
        status='draft',
        max_score=Decimal('100.00'),
        due_date=datetime.utcnow() + timedelta(days=7),
        teacher=teacher_user,
        classroom_id=classroom.id,
        allow_late_submissions=True,
        late_penalty_percent=Decimal('10.00'),
        max_attempts=3
    )


@pytest.fixture
def submission_model(db, assignment_model, student_user):
    """Create submission model."""
    return Submission.objects.create(
        id=uuid4(),
        assignment=assignment_model,
        student=student_user,
        status='draft',
        content="Student work",
        attempt_number=1
    )