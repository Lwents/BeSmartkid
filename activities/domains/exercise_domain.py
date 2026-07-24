import re
import uuid
from typing import TypedDict, Optional, List, Dict, Any, TYPE_CHECKING
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from django.utils import timezone

from activities.domains.question_domain import QuestionDomain

if TYPE_CHECKING:
    from activities.domains.exercise_attempt_domain import ExerciseAttemptDomain


# ---------- Helpers ----------
def now_utc() -> datetime:
    # timezone-aware now to keep datetime arithmetic consistent
    return timezone.now()

def normalize_text(s: str) -> str:
    s = s or ""
    s = s.strip().lower()
    s = re.sub(r'\s+', ' ', s)
    s = re.sub(r'[^\w\s]', '', s)  # remove punctuation for basic normalization
    return s

def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


class ExerciseDict(TypedDict):
    id: str
    lesson_id: str
    title: str
    type: str
    settings: Dict[str, Any]
    published: bool
    created_on: Optional[datetime]
    updated_on: Optional[datetime]


class ExerciseDomain:
    ALLOWED_TYPES = {"mcq", "short_answer", "matching", "quiz", "assignment"}  # Support both model choices and domain types
    def __init__(self, id: str, lesson_id: Optional[str], title: str, type: str,
                 settings: Optional[Dict[str,Any]] = None,
                 questions: Optional[List[QuestionDomain]] = None,
                 published: bool = False,
                 created_on: Optional[datetime] = None,
                 updated_on: Optional[datetime] = None):
        self.id = id
        self.lesson_id = lesson_id
        self.title = title
        self.type = type
        self.settings = settings or {}
        self.questions = questions or []
        self.published = published
        self.created_on = created_on
        self.updated_on = updated_on

    @classmethod
    def from_model(cls, model) -> "ExerciseDomain":
        q_domains = [QuestionDomain.from_model(q) for q in getattr(model, 'questions').all()] if hasattr(model, 'questions') else []
        settings = {}
        if hasattr(model, 'settings') and model.settings:
            settings_obj = model.settings
            if hasattr(settings_obj, '__dict__'):
                # ExerciseSettings model
                settings = {
                    'duration_seconds': getattr(settings_obj, 'time_limit_seconds', None),
                    'pass_score': getattr(settings_obj, 'pass_score', 50.0),
                    'max_attempts': getattr(settings_obj, 'max_attempts', None),
                    'shuffle_questions': getattr(settings_obj, 'shuffle_questions', True),
                    'shuffle_choices': getattr(settings_obj, 'shuffle_choices', True),
                    'description': getattr(settings_obj, 'description', None),
                    'level': getattr(settings_obj, 'level', None),
                    'course_id': getattr(settings_obj, 'course_id', None),
                }
                # Add scheduled_at if present
                scheduled_at = getattr(settings_obj, 'scheduled_at', None)
                if scheduled_at:
                    settings['scheduled_at'] = scheduled_at.isoformat() if hasattr(scheduled_at, 'isoformat') else str(scheduled_at)
                # Add end_at if present
                end_at = getattr(settings_obj, 'end_at', None)
                if end_at:
                    settings['end_at'] = end_at.isoformat() if hasattr(end_at, 'isoformat') else str(end_at)
            else:
                settings = settings_obj if isinstance(settings_obj, dict) else {}
        # Handle lesson_id - can be None
        lesson_id = None
        if hasattr(model, 'lesson_id') and model.lesson_id:
            lesson_id = str(model.lesson_id)
        elif hasattr(model, 'lesson') and model.lesson:
            lesson_id = str(model.lesson.id)
        return cls(
            id=str(model.id),
            lesson_id=lesson_id,
            title=model.title,
            type=model.type,
            settings=settings,
            questions=q_domains,
            published=getattr(model, 'published', False),
            created_on=getattr(model, 'created_on', None),
            updated_on=getattr(model, 'updated_on', None)
        )

    def validate(self):
        if not self.title:
            raise ValueError("Exercise title is required.")
        if self.type not in self.ALLOWED_TYPES:
            # allow unknown types but warn — here enforce
            raise ValueError(f"Invalid exercise type: {self.type}")
        # Questions can be empty on creation, will be added later
        # if not self.questions:
        #     raise ValueError("Exercise should contain at least one question.")
        for q in self.questions:
            q.validate()

    def total_possible_points(self) -> float:
        return sum(q.total_points() for q in self.questions)

    def can_attempt(self, student_attempt_count: int) -> bool:
        """
        Check if a student can attempt this exercise.
        
        Args:
            student_attempt_count: Number of attempts THIS SPECIFIC student has made
        
        Returns:
            True if student can attempt (either unlimited or under their limit)
        
        Note: max_attempts is per-student, NOT global. Multiple students can
        independently attempt the same exercise.
        """
        max_attempts = self.settings.get('max_attempts')
        if max_attempts is None:
            # No limit - student can attempt unlimited times
            return True
        # Check if student's attempt count is less than their personal limit
        return student_attempt_count < int(max_attempts)

    def create_attempt(self, student_id: Optional[int] = None):
        from activities.domains.exercise_attempt_domain import ExerciseAttemptDomain
        started = now_utc()
        metadata = {}
        # store per-exercise time_limit for attempt
        if 'time_limit_seconds' in self.settings and self.settings['time_limit_seconds']:
            metadata['time_limit_seconds'] = int(self.settings['time_limit_seconds'])
        return ExerciseAttemptDomain(
            id=str(uuid.uuid4()),
            exercise_id=self.id,
            student_id=student_id,
            started_at=started,
            finished_at=None,
            status="in_progress",
            score=None,
            metadata=metadata,
            exercise=self
        )
