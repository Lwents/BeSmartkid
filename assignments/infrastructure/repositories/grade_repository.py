# infrastructure/repositories/grade_repository.py
"""Repository implementation for Grade."""
from typing import Optional
from uuid import UUID
from decimal import Decimal

from ...domain.entities.grade import Grade
from ...domain.value_objects import Score
from ...domain.interfaces import IGradeRepository
from ...models import Grade


class GradeRepository(IGradeRepository):
    """Django ORM implementation of grade repository."""
    
    def save(self, grade: Grade) -> Grade:
        """Save grade to database."""
        # Calculate final score and percentage
        final_score_value = grade.score.points
        percentage = grade.score.percentage
        letter_grade = grade.score.to_letter_grade()
        
        model, created = Grade.objects.update_or_create(
            id=grade.id,
            defaults={
                'submission_id': grade.submission_id,
                'grader_id': grade.grader_id,
                'raw_score': grade.raw_score.points,
                'max_score': grade.raw_score.max_points,
                'late_penalty_applied': grade.late_penalty_applied,
                'final_score': final_score_value,
                'percentage': percentage,
                'letter_grade': letter_grade,
                'feedback': grade.feedback or '',
                'is_final': grade.is_final
            }
        )
        return self._to_entity(model)
    
    def get_by_submission(self, submission_id: UUID) -> Optional[Grade]:
        """Get grade for submission."""
        try:
            model = Grade.objects.get(submission_id=submission_id)
            return self._to_entity(model)
        except Grade.DoesNotExist:
            return None
    
    def _to_entity(self, model: Grade) -> Grade:
        """Convert ORM model to domain entity."""
        score = Score(points=model.raw_score, max_points=model.max_score)
        
        return Grade(
            id=model.id,
            submission_id=model.submission_id,
            grader_id=model.grader_id,
            score=score,
            feedback=model.feedback,
            graded_at=model.graded_at,
            is_final=model.is_final,
            late_penalty_applied=model.late_penalty_applied
        )