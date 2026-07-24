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
from activities.services.exceptions import NotFoundError, ValidationError, PermissionDenied
from activities.services.exercise_service import get_exercise



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
HintModel = getattr(apps.get_model('activities', 'Hint'), '__call__', None)
QuestionStatModel = getattr(apps.get_model('activities', 'QuestionStat'), '__call__', None)



# ----------------------
# Analytics
# ----------------------
def exercise_stats(exercise_id: str) -> Dict[str, Any]:
    qs = ExerciseAttemptModel.objects.filter(exercise_id=exercise_id)
    total = qs.count()
    finished_qs = qs.filter(finished_at__isnull=False)
    finished_count = finished_qs.count()
    avg_score = float(finished_qs.aggregate(avg=Avg("score"))["avg"] or 0)
    
    # Get pass score from exercise settings
    try:
        exercise = ExerciseModel.objects.get(id=exercise_id)
        pass_score = 50  # Default
        if hasattr(exercise, 'settings') and exercise.settings:
            pass_score = exercise.settings.pass_score or 50
    except ExerciseModel.DoesNotExist:
        pass_score = 50
    
    passed = finished_qs.filter(score__gte=pass_score).count()
    pass_rate = (passed / finished_count * 100) if finished_count > 0 else 0
    
    return {
        "exercise_id": exercise_id,
        "total_attempts": total,
        "submissions": finished_count,
        "avg_score": round(avg_score, 1),
        "avgScore": round(avg_score, 1),  # Alias for frontend
        "passed": passed,
        "pass_rate": round(pass_rate, 1),
        "passRate": round(pass_rate, 1),  # Alias for frontend
    }


def exercise_ranking(exercise_id: str, user_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Get ranking data for an exercise.
    Returns top students and current user's rank if user_id is provided.
    Only includes the best attempt for each student.
    """
    # Get all finished attempts
    finished_attempts = ExerciseAttemptModel.objects.filter(
        exercise_id=exercise_id,
        finished_at__isnull=False,
        score__isnull=False
    ).select_related("student", "student__profile").prefetch_related("answers")
    
    # Get exercise to calculate total questions
    try:
        exercise = ExerciseModel.objects.get(id=exercise_id)
        total_questions = exercise.questions.count()
    except ExerciseModel.DoesNotExist:
        total_questions = 0
    
    # Helper: duration in seconds (prefer metadata, otherwise non-negative delta)
    def duration_seconds(att) -> float:
        mt = None
        if att.metadata and isinstance(att.metadata, dict):
            mt = att.metadata.get("time_taken")
        if isinstance(mt, (int, float)) and mt > 0:
            return float(mt)
        if att.started_at and att.finished_at and att.finished_at >= att.started_at:
            try:
                delta = (att.finished_at - att.started_at).total_seconds()
                return max(1.0, delta)
            except Exception:
                return float("inf")
        return float("inf")

    # Group attempts by student and get the best attempt for each student
    # Best = highest score, if tie then shortest time
    student_best_attempts = {}
    for attempt in finished_attempts:
        if not attempt.student:
            continue
        
        student_id = attempt.student.id
        if student_id not in student_best_attempts:
            student_best_attempts[student_id] = attempt
        else:
            # Compare with existing best attempt
            existing = student_best_attempts[student_id]
            # Higher score wins
            if attempt.score > existing.score:
                student_best_attempts[student_id] = attempt
            elif attempt.score == existing.score:
                # Same score: shorter time wins
                existing_time = duration_seconds(existing)
                attempt_time = duration_seconds(attempt)
                if attempt_time < existing_time:
                    student_best_attempts[student_id] = attempt
    
    # Sort by score (desc) then by time (asc)
    sorted_attempts = sorted(
        student_best_attempts.values(),
        key=lambda a: (
            -a.score,  # Higher score first
            duration_seconds(a)  # Shorter time first
        )
    )
    
    # Build ranking list
    top_students = []
    user_rank = None
    user_stats = None
    current_rank = 1
    
    for attempt in sorted_attempts:
            
        # Calculate correct count from answers (only count answers where correct=True)
        correct_count = sum(1 for ans in attempt.answers.all() if ans.correct is True)
        
        # Calculate time taken (prefer metadata, otherwise non-negative delta)
        time_taken_raw = duration_seconds(attempt)
        time_taken = None if time_taken_raw == float("inf") else max(1, int(time_taken_raw))

        # Format time as MM:SS (ensure non-negative and valid)
        if time_taken is not None and time_taken > 0:
            minutes = int(time_taken // 60)
            seconds = int(time_taken % 60)
            time_str = f"{minutes:02d}:{seconds:02d}"
        else:
            # If no valid time, show 00:00
            time_str = "00:00"
        
        # Get student name + avatar from profile
        student_name = "Học viên"
        avatar_url = ""
        gender = ""
        if attempt.student:
            if hasattr(attempt.student, 'profile') and attempt.student.profile:
                profile = attempt.student.profile
                if getattr(profile, "display_name", None):
                    student_name = profile.display_name
                else:
                    student_name = attempt.student.username or "Học viên"
                avatar_url = getattr(profile, "avatar_url", "") or ""
                gender = getattr(profile, "gender", "") or ""
                if not avatar_url and isinstance(profile.metadata, dict):
                    avatar_url = profile.metadata.get("avatar") or profile.metadata.get("avatar_url") or ""
            else:
                student_name = attempt.student.username or "Học viên"
        
        student_data = {
            "student_id": attempt.student.id if attempt.student else None,
            "student_name": student_name,
            "name": student_name,
            "attempt_id": str(attempt.id),
            "avatar": avatar_url,
            "gender": gender,
            "score": round(attempt.score or 0, 1),
            "total_score": round(attempt.score or 0, 1),
            "correct_count": correct_count,
            "total_count": total_questions,
            "time_taken": time_str,
        }
        
        # Check if this is the current user
        if user_id and attempt.student.id == user_id:
            user_rank = current_rank
            user_stats = {
                "rank": current_rank,
                "attempt_id": str(attempt.id),
                "score": round(attempt.score or 0, 1),
                "total_score": round(attempt.score or 0, 1),
                "correct_count": correct_count,
                "total_count": total_questions,
                "time_taken": time_str,
                "avatar": avatar_url,
                "gender": gender,
            }
        
        # Add to top students (limit to top 100)
        if len(top_students) < 100:
            top_students.append(student_data)
        
        current_rank += 1
    
    return {
        "top_students": top_students,
        "my_stats": user_stats,
    }


def export_results_csv(exercise_id: str) -> Tuple[str, bytes]:
    qs = ExerciseAttemptModel.objects.filter(exercise_id=exercise_id).select_related("student").prefetch_related("answers__question")
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["attempt_id", "student_id", "score", "question_id", "answer", "correct"])
    for att in qs:
        for ans in att.answers.all():
            writer.writerow([att.id, att.student_id, att.score, ans.question_id, ans.answer, ans.correct])
    return f"exercise_{exercise_id}_results.csv", buf.getvalue().encode("utf-8")
