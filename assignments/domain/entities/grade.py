# domain/entities/grade.py
"""Grade entity with business logic."""
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from ..value_objects import Score


class Grade:
    """
    Grade entity representing assessment result.
    
    Pure domain entity for grading logic.
    """
    
    def __init__(
        self,
        id: UUID,
        submission_id: UUID,
        grader_id: UUID,
        score: Score,
        feedback: Optional[str] = None,
        graded_at: Optional[datetime] = None,
        is_final: bool = True,
        late_penalty_applied: Decimal = Decimal('0')
    ):
        self.id = id
        self.submission_id = submission_id
        self.grader_id = grader_id
        self._raw_score = score
        self.feedback = feedback
        self.graded_at = graded_at or datetime.utcnow()
        self.is_final = is_final
        self.late_penalty_applied = late_penalty_applied
    
    @property
    def raw_score(self) -> Score:
        """Score before late penalty."""
        return self._raw_score
    
    @property
    def score(self) -> Score:
        """Final score with late penalty applied."""
        if self.late_penalty_applied == 0:
            return self._raw_score
        return self._raw_score.apply_penalty(self.late_penalty_applied)
    
    def update_feedback(self, feedback: str):
        """Update grading feedback."""
        self.feedback = feedback
    
    def mark_as_draft(self):
        """Mark grade as draft (not final)."""
        self.is_final = False
    
    def finalize(self):
        """Finalize grade."""
        self.is_final = True