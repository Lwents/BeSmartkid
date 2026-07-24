from typing import Optional, List, Dict, Any, Tuple
from django.apps import apps
from django.db import transaction
from django.db.models import Avg, F
from django.utils import timezone
import csv
import io

# Domain imports
from activities.domains.choice_domain import (
    ChoiceDomain,
)
from activities.domains.exercise_answer_domain import ExerciseAnswerDomain
from activities.domains.exercise_attempt_domain import ExerciseAttemptDomain
from activities.domains.exercise_domain import ExerciseDomain
from activities.domains.question_domain import QuestionDomain
from activities.services.exceptions import NotFoundError



# Models
ExerciseModel = apps.get_model('activities', 'Exercise')
QuestionModel = apps.get_model('activities', 'Question')
ChoiceModel = apps.get_model('activities', 'Choice')
ExerciseAttemptModel = apps.get_model('activities', 'ExerciseAttempt')
ExerciseAnswerModel = apps.get_model('activities', 'ExerciseAnswer')

# Optional models
try:
    ExerciseSettingsModel = apps.get_model('activities', 'ExerciseSettings')
except LookupError:
    ExerciseSettingsModel = None

try:
    HintModel = apps.get_model('activities', 'Hint')
except LookupError:
    HintModel = None

try:
    QuestionStatModel = apps.get_model('activities', 'QuestionStat')
except LookupError:
    QuestionStatModel = None


# ----------------------
# Exercise CRUD
# ----------------------
def get_exercise(exercise_id: str) -> ExerciseDomain:
    try:
        m = ExerciseModel.objects.prefetch_related('questions__choices').get(id=exercise_id)
    except ExerciseModel.DoesNotExist:
        raise NotFoundError("Exercise not found")
    return ExerciseDomain.from_model(m)


def list_exercises(filters: Dict[str, Any] = None) -> List[ExerciseDomain]:
    qs = ExerciseModel.objects.all()
    if filters:
        if filters.get("lesson_id"):
            qs = qs.filter(lesson_id=filters["lesson_id"])
        if filters.get("published") is not None:
            qs = qs.filter(published=filters["published"])
    return [ExerciseDomain.from_model(m) for m in qs.prefetch_related("questions__choices")]


@transaction.atomic
def save_exercise(domain: ExerciseDomain) -> ExerciseDomain:
    """Create or update exercise with nested questions/choices."""
    # lesson_id can be None for standalone exercises
    defaults = {
        'title': domain.title,
        'type': domain.type,
        'published': domain.published,  # Update published status
    }
    if domain.lesson_id:
        defaults['lesson_id'] = domain.lesson_id
    # Note: settings stored in ExerciseSettings model, not directly in Exercise
    ex, _ = ExerciseModel.objects.update_or_create(
        id=domain.id,
        defaults=defaults
    )

    # Sync questions
    seen_qids = []
    for qd in domain.questions:
        q, _ = QuestionModel.objects.update_or_create(
            id=qd.id,
            defaults=dict(exercise=ex, prompt=qd.prompt, meta=qd.meta or {})
        )
        seen_qids.append(q.id)
        # Sync choices
        seen_cids = []
        for cd in qd.choices:
            c, _ = ChoiceModel.objects.update_or_create(
                id=cd.id,
                defaults=dict(
                    question=q,
                    text=cd.text,
                    is_correct=cd.is_correct,
                    position=cd.position,
                )
            )
            seen_cids.append(c.id)
        q.choices.exclude(id__in=seen_cids).delete()
    ex.questions.exclude(id__in=seen_qids).delete()

    # Save settings to ExerciseSettings model
    if ExerciseSettingsModel and domain.settings:
        from datetime import datetime
        settings_data = domain.settings.copy()
        
        # Handle scheduled_at if present
        scheduled_at = settings_data.get('scheduled_at')
        if scheduled_at:
            # Parse ISO datetime string to datetime object
            if isinstance(scheduled_at, str):
                try:
                    scheduled_at = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    scheduled_at = None
        else:
            scheduled_at = None
        
        # Handle end_at if present
        end_at = settings_data.get('end_at')
        if end_at:
            # Parse ISO datetime string to datetime object
            if isinstance(end_at, str):
                try:
                    end_at = datetime.fromisoformat(end_at.replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    end_at = None
        else:
            end_at = None

        # Normalize max_attempts (None -> unlimited)
        # IMPORTANT: max_attempts is per-student, NOT global
        # If None or not set, students can attempt unlimited times
        # If set to a number, each student can attempt that many times independently
        max_attempts = settings_data.get('max_attempts')
        try:
            if max_attempts is not None and max_attempts != '':
                max_attempts = int(max_attempts)
                # Ensure it's a positive number
                if max_attempts <= 0:
                    max_attempts = None  # Invalid value, treat as unlimited
            else:
                max_attempts = None  # No limit - allow unlimited attempts per student
        except (TypeError, ValueError):
            max_attempts = None  # Invalid value, treat as unlimited
        
        # Get existing settings if any
        defaults = {
            'time_limit_seconds': settings_data.get('duration_seconds'),
            # Default pass score: 10 (thay vì 50) nếu không được cung cấp
            'pass_score': settings_data.get('pass_score', 10.0),
            'shuffle_questions': settings_data.get('shuffle_questions', True),
            'shuffle_choices': settings_data.get('shuffle_choices', True),
            'max_attempts': max_attempts,
            'scheduled_at': scheduled_at,
            'end_at': end_at,
            'course_id': settings_data.get('course_id'),
        }
        
        # Check if show_answers field exists before adding
        try:
            ExerciseSettingsModel._meta.get_field('show_answers')
            defaults['show_answers'] = settings_data.get('show_answers', 'always')
        except Exception:
            pass  # Field doesn't exist yet, skip it
        
        # Update or create ExerciseSettings
        ExerciseSettingsModel.objects.update_or_create(
            exercise=ex,
            defaults=defaults
        )

    return ExerciseDomain.from_model(ex)


def delete_exercise(exercise_id: str) -> bool:
    deleted, _ = ExerciseModel.objects.filter(id=exercise_id).delete()
    if not deleted:
        raise NotFoundError("Exercise not found")
    return True
