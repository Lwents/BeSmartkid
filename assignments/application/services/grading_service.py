# application/services/grading_service.py
"""Grading service for use cases."""
from decimal import Decimal
from uuid import UUID, uuid4

from ..dto.assignment_dto import GradeSubmissionDTO
from ...domain.entities.grade import Grade
from ...domain.value_objects import Score
from ...domain.interfaces import (
    ISubmissionRepository,
    IGradeRepository,
    IAssignmentRepository
)
from ...domain.exceptions import InvalidGrade, AssignmentNotFound


class GradingService:
    """Application service for grading use cases."""
    
    def __init__(
        self,
        grade_repo: IGradeRepository,
        submission_repo: ISubmissionRepository,
        assignment_repo: IAssignmentRepository
    ):
        self.grade_repo = grade_repo
        self.submission_repo = submission_repo
        self.assignment_repo = assignment_repo
    
    def grade_submission(self, dto: GradeSubmissionDTO) -> Grade:
        """Grade a submission."""
        submission = self.submission_repo.get_by_id(dto.submission_id)
        if not submission:
            raise InvalidGrade(f"Submission {dto.submission_id} not found")
        
        assignment = self.assignment_repo.get_by_id(submission.assignment_id)
        if not assignment:
            raise AssignmentNotFound(f"Assignment {submission.assignment_id} not found")
        
        # Create score
        score = Score(points=dto.score, max_points=dto.max_score)
        
        # Calculate late penalty
        late_penalty = Decimal('0')
        if submission.is_late:
            late_penalty = assignment.calculate_late_penalty_for_submission(
                submission.submitted_at
            )
        
        # Create grade
        grade = Grade(
            id=uuid4(),
            submission_id=dto.submission_id,
            grader_id=dto.grader_id,
            score=score,
            feedback=dto.feedback,
            late_penalty_applied=late_penalty
        )
        
        # Apply to submission
        submission.grade(grade)
        self.submission_repo.save(submission)
        
        # Save grade
        return self.grade_repo.save(grade)