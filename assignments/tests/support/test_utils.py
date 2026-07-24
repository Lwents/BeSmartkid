# tests/support/test_utils.py
"""Test utilities."""
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from assignments.domain.entities.assignment import Assignment
from assignments.domain.value_objects import (
    DueDate,
    LatePenalty,
    AssignmentType
)


def create_test_assignment(**kwargs):
    """Create test assignment entity."""
    defaults = {
        'id': uuid4(),
        'title': 'Test Assignment',
        'description': 'Test Description',
        'assignment_type': AssignmentType.HOMEWORK,
        'max_score': Decimal('100.00'),
        'due_dates': DueDate(
            due_date=datetime.utcnow() + timedelta(days=7),
            available_from=datetime.utcnow(),
            available_until=datetime.utcnow() + timedelta(days=14)
        ),
        'late_penalty': LatePenalty(Decimal('10.00')),
        'max_attempts': 3,
        'allow_late_submissions': True,
        'is_group_assignment': False,
        'requires_parent_consent': False,
        'age_appropriate_level': 1,
        'auto_grade': False,
        'teacher_id': uuid4(),
        'classroom_id': uuid4(),
        'status': 'draft'
    }
    defaults.update(kwargs)
    return Assignment(**defaults)