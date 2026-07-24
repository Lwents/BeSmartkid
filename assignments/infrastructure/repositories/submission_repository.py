# infrastructure/repositories/submission_repository.py
"""Repository implementation for Submission."""
from typing import List, Optional
from uuid import UUID

from ...domain.entities.submission import Submission
from ...domain.value_objects import SubmissionStatus
from ...domain.interfaces import ISubmissionRepository
from ...models import Submission


class SubmissionRepository(ISubmissionRepository):
    """Django ORM implementation of submission repository."""
    
    def save(self, submission: Submission) -> Submission:
        """Save submission to database."""
        model, created = Submission.objects.update_or_create(
            id=submission.id,
            defaults={
                'assignment_id': submission.assignment_id,
                'student_id': submission.student_id,
                'group_id': submission.group_id,
                'status': submission.status.value,
                'content': submission.content,
                'attempt_number': submission.attempt_number,
                'submitted_at': submission.submitted_at,
                'is_late': submission.is_late,
                'late_days': submission.late_days,
                'version': submission.version + 1 if not created else 1
            }
        )
        return self._to_entity(model)
    
    def get_by_id(self, submission_id: UUID) -> Optional[Submission]:
        """Get submission by ID."""
        try:
            model = Submission.objects.get(id=submission_id)
            return self._to_entity(model)
        except Submission.DoesNotExist:
            return None
    
    def list_by_assignment(self, assignment_id: UUID) -> List[Submission]:
        """List submissions for assignment."""
        models = Submission.objects.filter(
            assignment_id=assignment_id
        ).order_by('-created_at')
        return [self._to_entity(m) for m in models]
    
    def get_student_submission(self, assignment_id: UUID, student_id: UUID) -> Optional[Submission]:
        """Get student's submission for assignment."""
        try:
            model = Submission.objects.filter(
                assignment_id=assignment_id,
                student_id=student_id
            ).order_by('-attempt_number').first()
            return self._to_entity(model) if model else None
        except Submission.DoesNotExist:
            return None
    
    def _to_entity(self, model: Submission) -> Submission:
        """Convert ORM model to domain entity."""
        return Submission(
            id=model.id,
            assignment_id=model.assignment_id,
            student_id=model.student_id,
            status=SubmissionStatus(model.status),
            content=model.content,
            attempt_number=model.attempt_number,
            submitted_at=model.submitted_at,
            created_at=model.created_at,
            group_id=model.group_id,
            is_late=model.is_late,
            late_days=model.late_days,
            version=model.version
        )