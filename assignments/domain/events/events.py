# assignments/domain/events/events.py
"""
Domain events for the assignments module.
These events represent things that have happened in the domain.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional



@dataclass(frozen=True)
class DomainEvent:
    """Base class for all domain events."""
    occurred_at: datetime
    
    def __post_init__(self):
        """Ensure occurred_at is set."""
        if not self.occurred_at:
            object.__setattr__(self, 'occurred_at', datetime.utcnow())


@dataclass(frozen=True)
class AssignmentCreatedEvent(DomainEvent):
    """Event fired when an assignment is created."""
    assignment_id: str
    title: str
    teacher_id: str
    classroom_id: Optional[str]


@dataclass(frozen=True)
class AssignmentPublishedEvent(DomainEvent):
    """Event fired when an assignment is published."""
    assignment_id: str
    title: str
    due_date: Optional[datetime]
    published_at: datetime


@dataclass(frozen=True)
class AssignmentArchivedEvent(DomainEvent):
    """Event fired when an assignment is archived."""
    assignment_id: str
    archived_at: datetime


@dataclass(frozen=True)
class SubmissionCreatedEvent(DomainEvent):
    """Event fired when a submission is created."""
    submission_id: str
    assignment_id: str
    student_id: str
    attempt_number: int


@dataclass(frozen=True)
class SubmissionSubmittedEvent(DomainEvent):
    """Event fired when a submission is submitted for grading."""
    submission_id: str
    assignment_id: str
    student_id: str
    submitted_at: datetime
    is_late: bool
    attempt_number: int


@dataclass(frozen=True)
class SubmissionGradedEvent(DomainEvent):
    """Event fired when a submission is graded."""
    submission_id: str
    assignment_id: str
    student_id: str
    raw_score: float
    final_score: float
    graded_by: str
    graded_at: datetime


@dataclass(frozen=True)
class SubmissionReturnedEvent(DomainEvent):
    """Event fired when a graded submission is returned to student."""
    submission_id: str
    assignment_id: str
    student_id: str
    returned_at: datetime


@dataclass(frozen=True)
class LatePenaltyAppliedEvent(DomainEvent):
    """Event fired when a late penalty is applied to a submission."""
    submission_id: str
    assignment_id: str
    student_id: str
    penalty_percent: float
    days_late: int

