# domain/entities/submission.py
"""Submission entity with business logic."""
from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from uuid import UUID
from enum import Enum

from ..value_objects import SubmissionStatus, Score, Grade
from ..exceptions import InvalidGrade


class SubmissionStatus(str, Enum):
    """Submission status enumeration."""
    DRAFT = "draft"
    SUBMITTED = "submitted"
    GRADED = "graded"
    RETURNED = "returned"
    REJECTED = "rejected"

class Submission:
    """
    Submission entity representing a student's assignment submission.
    
    Pure domain entity with business logic for submission lifecycle.
    """
    
    def __init__(
        self,
        id: UUID,
        assignment_id: UUID,
        student_id: UUID,
        status: SubmissionStatus = SubmissionStatus.DRAFT,
        content: Optional[str] = None,
        attempt_number: int = 1,
        submitted_at: Optional[datetime] = None,
        created_at: Optional[datetime] = None,
        group_id: Optional[UUID] = None,
        is_late: bool = False,
        late_days: int = 0,
        version: int = 1
    ):
        self.id = id
        self.assignment_id = assignment_id
        self.student_id = student_id
        self._status = status
        self.content = content
        self.attempt_number = attempt_number
        self.submitted_at = submitted_at
        self.created_at = created_at or datetime.utcnow()
        self.group_id = group_id
        self.is_late = is_late
        self.late_days = late_days
        self.version = version
        self._grade: Optional["Grade"] = None
    
    @property
    def status(self) -> SubmissionStatus:
        return self._status
    
    def is_submitted(self) -> bool:
        """Check if submission has been submitted."""
        return self._status in [
            SubmissionStatus.SUBMITTED,
            SubmissionStatus.GRADED,
            SubmissionStatus.RETURNED
        ]
    
    def submit(self, submission_time: datetime, late_info: tuple[bool, int]):
        """Submit the assignment."""
        if self._status != SubmissionStatus.DRAFT:
            raise ValueError("Can only submit draft submissions")
        
        self._status = SubmissionStatus.SUBMITTED
        self.submitted_at = submission_time
        self.is_late, self.late_days = late_info
    
    def grade(self, grade: 'Grade'):
        """Apply grade to submission."""
        if not self.is_submitted():
            raise InvalidGrade("Cannot grade unsubmitted work")
        
        self._grade = grade
        self._status = SubmissionStatus.GRADED
    
    def return_to_student(self):
        """Return graded submission to student."""
        if self._status != SubmissionStatus.GRADED:
            raise ValueError("Can only return graded submissions")
        
        self._status = SubmissionStatus.RETURNED
    
    def reject(self):
        """Reject submission (e.g., plagiarism, inappropriate content)."""
        self._status = SubmissionStatus.REJECTED
    
    @property
    def final_score(self) -> Optional[Score]:
        """Get final score with late penalty applied."""
        if not self._grade:
            return None
        return self._grade.score