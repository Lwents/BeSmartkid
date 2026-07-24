from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from uuid import UUID, uuid4

from ..value_objects import DueDate, Score, LatePenalty, AssignmentType
from ..exceptions import (
    AssignmentNotAvailable,
    SubmissionNotAllowed,
    LateSubmissionNotAllowed,
    InappropriateContent
)



class Assignment:
    """
    Assignment entity representing a homework/assessment task.
    
    This is a pure domain entity with no framework dependencies.
    All business logic for assignments lives here.
    """
    
    # Child safety word list (simplified)
    PROHIBITED_WORDS = {'inappropriate', 'violent', 'dangerous'}
    
    def __init__(
        self,
        id: UUID,
        title: str,
        description: str,
        assignment_type: AssignmentType,
        max_score: Decimal,
        due_dates: DueDate,
        late_penalty: Optional[LatePenalty] = None,
        max_attempts: int = 1,
        allow_late_submissions: bool = True,
        is_group_assignment: bool = False,
        requires_parent_consent: bool = False,
        age_appropriate_level: int = 1,
        auto_grade: bool = False,
        teacher_id: Optional[UUID] = None,
        classroom_id: Optional[UUID] = None,
        created_at: Optional[datetime] = None,
        status: str = 'draft'
    ):
        self.id = id
        self._title = title
        self._description = description
        self.assignment_type = assignment_type
        self.max_score = max_score
        self.due_dates = due_dates
        self.late_penalty = late_penalty or LatePenalty(Decimal('0'))
        self.max_attempts = max_attempts
        self.allow_late_submissions = allow_late_submissions
        self.is_group_assignment = is_group_assignment
        self.requires_parent_consent = requires_parent_consent
        self.age_appropriate_level = age_appropriate_level
        self.auto_grade = auto_grade
        self.teacher_id = teacher_id
        self.classroom_id = classroom_id
        self.created_at = created_at or datetime.utcnow()
        self._status = status
        
        # Validate on construction
        self._validate_content()
        self._validate_age_appropriate()
    
    @property
    def title(self) -> str:
        return self._title
    
    @title.setter
    def title(self, value: str):
        self._title = value
        self._validate_content()
    
    @property
    def description(self) -> str:
        return self._description
    
    @description.setter
    def description(self, value: str):
        self._description = value
        self._validate_content()
    
    @property
    def status(self) -> str:
        return self._status
    
    def _validate_content(self):
        """Validate content doesn't contain prohibited words."""
        text = f"{self._title} {self._description}".lower()
        for word in self.PROHIBITED_WORDS:
            if word in text:
                raise InappropriateContent(f"Content contains prohibited word: {word}")
    
    def _validate_age_appropriate(self):
        """Validate age appropriateness."""
        if self.age_appropriate_level < 1 or self.age_appropriate_level > 5:
            raise ValueError("age_appropriate_level must be between 1 and 5")
    
    def publish(self):
        """Publish assignment to students."""
        if self._status == 'published':
            raise ValueError("Assignment is already published")
        self._status = 'published'
    
    def archive(self):
        """Archive assignment."""
        self._status = 'archived'
    
    def can_submit(self, current_time: datetime, attempt_number: int) -> bool:
        """Check if submission is allowed."""
        if self._status != 'published':
            return False
        
        if not self.due_dates.is_available(current_time):
            return False
        
        if self.max_attempts > 0 and attempt_number > self.max_attempts:
            return False
        
        return True
    
    def validate_submission(self, current_time: datetime, attempt_number: int):
        """Validate submission is allowed, raise exception if not."""
        if self._status != 'published':
            raise SubmissionNotAllowed("Assignment is not published")
        
        if not self.due_dates.is_available(current_time):
            raise AssignmentNotAvailable("Assignment is not currently available")
        
        if self.due_dates.is_past_due(current_time) and not self.allow_late_submissions:
            raise LateSubmissionNotAllowed("Late submissions are not allowed")
        
        if self.max_attempts > 0 and attempt_number > self.max_attempts:
            raise SubmissionNotAllowed(f"Maximum attempts ({self.max_attempts}) exceeded")
    
    def calculate_late_penalty_for_submission(self, submission_time: datetime) -> Decimal:
        """Calculate late penalty percentage for a submission."""
        if not self.due_dates.is_past_due(submission_time):
            return Decimal('0')
        
        days_late = self.due_dates.days_late(submission_time)
        return self.late_penalty.calculate_penalty(days_late)