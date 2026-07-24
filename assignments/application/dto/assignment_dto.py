# application/dto/assignment_dto.py
"""Data Transfer Objects for Assignment use cases."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID


@dataclass
class CreateAssignmentDTO:
    """DTO for creating assignment."""
    title: str
    description: str
    assignment_type: str
    max_score: Decimal
    due_date: Optional[datetime]
    available_from: Optional[datetime]
    available_until: Optional[datetime]
    teacher_id: UUID
    classroom_id: Optional[UUID] = None
    allow_late_submissions: bool = True
    late_penalty_percent: Decimal = Decimal('0')
    max_attempts: int = 1
    is_group_assignment: bool = False
    requires_parent_consent: bool = False
    age_appropriate_level: int = 1
    auto_grade: bool = False


@dataclass
class AssignmentResponseDTO:
    """DTO for assignment response."""
    id: UUID
    title: str
    description: str
    assignment_type: str
    max_score: Decimal
    status: str
    due_date: Optional[datetime]
    created_at: datetime
    teacher_id: Optional[UUID]
    classroom_id: Optional[UUID]


@dataclass
class SubmitAssignmentDTO:
    """DTO for submitting assignment."""
    assignment_id: UUID
    student_id: UUID
    content: Optional[str] = None
    submission_time: Optional[datetime] = None


@dataclass
class GradeSubmissionDTO:
    """DTO for grading submission."""
    submission_id: UUID
    grader_id: UUID
    score: Decimal
    max_score: Decimal
    feedback: Optional[str] = None