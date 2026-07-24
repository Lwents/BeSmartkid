# application/services/submission_service.py
"""Submission service for use cases."""
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from ..dto.assignment_dto import SubmitAssignmentDTO
from ...domain.entities.submission import Submission
from ...domain.interfaces import IAssignmentRepository, ISubmissionRepository
from ...domain.exceptions import AssignmentNotFound, SubmissionNotAllowed
from ...domain.value_objects import SubmissionStatus


class SubmissionService:
    """Application service for submission use cases."""
    
    def __init__(
        self,
        submission_repo: ISubmissionRepository,
        assignment_repo: IAssignmentRepository
    ):
        self.submission_repo = submission_repo
        self.assignment_repo = assignment_repo
    
    def create_submission(self, dto: SubmitAssignmentDTO) -> Submission:
        """Create draft submission."""
        assignment = self.assignment_repo.get_by_id(dto.assignment_id)
        if not assignment:
            raise AssignmentNotFound(f"Assignment {dto.assignment_id} not found")
        
        # Check for existing submission
        existing = self.submission_repo.get_student_submission(
            dto.assignment_id,
            dto.student_id
        )
        
        attempt_number = 1
        if existing:
            attempt_number = existing.attempt_number + 1
        
        # Validate can submit
        current_time = dto.submission_time or datetime.utcnow()
        assignment.validate_submission(current_time, attempt_number)
        
        # Create submission
        submission = Submission(
            id=uuid4(),
            assignment_id=dto.assignment_id,
            student_id=dto.student_id,
            content=dto.content,
            attempt_number=attempt_number,
            status=SubmissionStatus.DRAFT
        )
        
        return self.submission_repo.save(submission)
    
    def submit_assignment(self, submission_id: UUID) -> Submission:
        """Submit assignment for grading."""
        submission = self.submission_repo.get_by_id(submission_id)
        if not submission:
            raise SubmissionNotAllowed(f"Submission {submission_id} not found")
        
        assignment = self.assignment_repo.get_by_id(submission.assignment_id)
        if not assignment:
            raise AssignmentNotFound(f"Assignment {submission.assignment_id} not found")
        
        # Calculate late info
        submission_time = datetime.utcnow()
        is_late = assignment.due_dates.is_past_due(submission_time)
        late_days = 0
        if is_late:
            late_days = assignment.due_dates.days_late(submission_time)
        
        # Submit
        submission.submit(submission_time, (is_late, late_days))
        
        return self.submission_repo.save(submission)