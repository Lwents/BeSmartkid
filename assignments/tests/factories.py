# tests/factories.py
"""Factory Boy factories for test data."""
import factory
from factory.django import DjangoModelFactory
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from assignments.models import (
    Assignment,
    Submission,
    Grade
)


class AssignmentFactory(DjangoModelFactory):
    """Factory for Assignment model."""
    
    class Meta:
        model = Assignment
    
    id = factory.LazyFunction(uuid4)
    title = factory.Sequence(lambda n: f"Assignment {n}")
    description = factory.Faker('text')
    assignment_type = 'homework'
    status = 'draft'
    max_score = Decimal('100.00')
    due_date = factory.LazyFunction(lambda: datetime.utcnow() + timedelta(days=7))
    allow_late_submissions = True
    late_penalty_percent = Decimal('10.00')
    max_attempts = 3
    age_appropriate_level = 1


class SubmissionFactory(DjangoModelFactory):
    """Factory for Submission model."""
    
    class Meta:
        model = Submission
    
    id = factory.LazyFunction(uuid4)
    assignment = factory.SubFactory(AssignmentFactory)
    status = 'draft'
    content = factory.Faker('text')
    attempt_number = 1


class GradeFactory(DjangoModelFactory):
    """Factory for Grade model."""
    
    class Meta:
        model = Grade
    
    id = factory.LazyFunction(uuid4)
    submission = factory.SubFactory(SubmissionFactory)
    raw_score = Decimal('85.00')
    max_score = Decimal('100.00')
    late_penalty_applied = Decimal('0.00')
    final_score = Decimal('85.00')
    percentage = Decimal('85.00')
    letter_grade = 'B'
    is_final = True