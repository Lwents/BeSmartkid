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
from activities.services.exercise_access_service import (
    can_manage_exercise,
    student_can_access_exercise,
)



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
# Attempt lifecycle
# ----------------------
def start_attempt(exercise_id: str, student_user) -> ExerciseAttemptDomain:
    """
    Start a new exam attempt for a student.
    
    IMPORTANT: Each student can independently attempt the exam.
    - Multiple students can take the same exam simultaneously
    - Each student has their own attempt count (max_attempts is per-student, not global)
    - Only restrictions are:
      1. Exercise must be published
      2. Exercise must not have expired (end_at check)
      3. Student must not exceed their personal max_attempts limit
    """
    from django.utils import timezone
    from django.apps import apps
    
    exercise = get_exercise(exercise_id)
    student_id = getattr(student_user, "id", None)
    if not student_id:
        raise ValidationError("Không xác định được người dùng để bắt đầu bài kiểm tra.")

    try:
        exercise_model = ExerciseModel.objects.select_related(
            "settings", "lesson__module__course"
        ).get(id=exercise_id)
    except ExerciseModel.DoesNotExist:
        raise NotFoundError("Exercise not found")
    if not student_can_access_exercise(student_user, exercise_model):
        raise PermissionDenied(
            "Bạn cần tham gia khóa học và mở khóa nội dung trước khi làm bài kiểm tra."
        )
    
    # Check if exercise is published
    if not exercise.published:
        raise ValidationError("Exercise is not published yet.")
    
    # Check if exercise has expired (end_at has passed)
    # This is the ONLY global restriction - if deadline passed, NO student can start
    ExerciseSettingsModel = apps.get_model('activities', 'ExerciseSettings')
    try:
        settings = ExerciseSettingsModel.objects.get(exercise_id=exercise_id)
        if settings.end_at and timezone.now() >= settings.end_at:
            raise ValidationError("Exercise has closed. The deadline has passed.")
    except ExerciseSettingsModel.DoesNotExist:
        pass  # No settings, allow attempt
    
    # Check if THIS SPECIFIC STUDENT already has an attempt
    # CRITICAL: This filter is per-student only. Other students' attempts are NOT considered.
    attempt_qs = ExerciseAttemptModel.objects.filter(
        exercise_id=exercise_id,
        student_id=student_id  # ONLY count attempts by THIS specific student
    ).order_by('-started_at')
    existing_attempt = attempt_qs.first()

    # If student has an unfinished attempt, return it to continue
    if existing_attempt and existing_attempt.finished_at is None:
        return ExerciseAttemptDomain.from_model(existing_attempt, exercise)

    # Check if THIS STUDENT has exceeded their personal attempt limit
    # max_attempts is per-student, NOT global. Each student has their own limit.
    attempt_count = attempt_qs.count()
    if not exercise.can_attempt(attempt_count):
        raise ValidationError(
            "Em đã dùng hết số lượt làm bài. Hãy xem lại kết quả và bảng xếp hạng nhé!"
        )

    # Create new attempt
    attempt_domain = exercise.create_attempt(student_id=student_id)
    attempt_model = ExerciseAttemptModel.objects.create(
        id=attempt_domain.id,
        exercise_id=exercise_id,
        student=student_user,
        metadata=attempt_domain.metadata or {},
        started_at=attempt_domain.started_at,
    )
    return ExerciseAttemptDomain.from_model(attempt_model, exercise)


def submit_answer(attempt_id: str, question_id: str, answer_payload: Dict[str, Any], actor_user) -> ExerciseAnswerDomain:
    try:
        att = ExerciseAttemptModel.objects.get(id=attempt_id)
    except ExerciseAttemptModel.DoesNotExist:
        raise NotFoundError("Attempt not found")

    exercise = ExerciseDomain.from_model(att.exercise)
    attempt = ExerciseAttemptDomain.from_model(att, exercise_domain=exercise)

    if actor_user.id != attempt.student_id and not actor_user.is_staff:
        raise PermissionDenied("Not allowed to submit answer for this attempt")

    # check status
    # ExerciseAttempt không có cột status nên domain luôn đọc 'in_progress';
    # finished_at là dữ liệu thật đã lưu -> dùng nó để chặn nộp lại lượt đã xong.
    if att.finished_at is not None or attempt.status != attempt.STATUS_IN_PROGRESS:
        raise ValidationError("Attempt already finished")

    try:
        question = QuestionDomain.from_model(QuestionModel.objects.get(id=question_id))
    except QuestionModel.DoesNotExist:
        raise NotFoundError(f"Question {question_id} not found")
    answer_domain = attempt.add_or_update_answer(question, answer_payload)

    ExerciseAnswerModel.objects.update_or_create(
        attempt=att, question_id=question_id,
        defaults={"answer": answer_domain.answer, "correct": answer_domain.correct}
    )

    attempt.compute_score()
    att.score = attempt.score
    att.metadata = attempt.metadata
    att.save()

    return answer_domain


def finalize_attempt(attempt_id: str, actor_user=None, force=False) -> Dict[str, Any]:
    try:
        att = ExerciseAttemptModel.objects.get(id=attempt_id)
    except ExerciseAttemptModel.DoesNotExist:
        raise NotFoundError("Attempt not found")

    if not actor_user:
        raise PermissionDenied("Không xác định được người dùng nộp bài.")
    if not force and actor_user.id != att.student_id:
        raise PermissionDenied("Không được phép nộp bài của học sinh khác.")

    # Chặn nộp lại lượt đã kết thúc (trừ khi staff dùng force) để điểm không bị ghi đè.
    if att.finished_at is not None and not force:
        raise ValidationError("Attempt already finished")

    exercise = ExerciseDomain.from_model(att.exercise)
    attempt = ExerciseAttemptDomain.from_model(att, exercise_domain=exercise)

    if force:
        if not (actor_user and actor_user.is_staff):
            raise PermissionDenied("Only staff may force finalize.")
        attempt.finalize()
    else:
        attempt.finalize()

    att.score = attempt.score
    att.finished_at = attempt.finished_at
    att.metadata = attempt.metadata
    att.save()

    return attempt.summary()


def regrade_attempt(attempt_id: str) -> Dict[str, Any]:
    try:
        att = ExerciseAttemptModel.objects.get(id=attempt_id)
    except ExerciseAttemptModel.DoesNotExist:
        raise NotFoundError("Attempt not found")

    exercise = ExerciseDomain.from_model(att.exercise)
    attempt = ExerciseAttemptDomain.from_model(att, exercise_domain=exercise)

    # rescore all answers
    total = 0.0
    for ans in att.answers.all():
        q = QuestionDomain.from_model(ans.question)
        result = q.score_answer(ans.answer or {})
        ans.answer.update(score=result.get("score", 0))
        ans.correct = result.get("correct", False)
        ans.save()
        total += ans.answer["score"]

    exercise_total = exercise.total_possible_points()
    attempt.score = round((total / exercise_total) * 100, 2) if exercise_total else total
    att.score = attempt.score
    att.save()

    return {"attempt_id": attempt_id, "new_score": attempt.score}


def get_attempt_summary(attempt_id: str) -> Dict[str, Any]:
    # Include profile to return class information alongside attempt summary
    att = ExerciseAttemptModel.objects.select_related("student__profile", "exercise").get(id=attempt_id)
    exercise = ExerciseDomain.from_model(att.exercise)
    attempt = ExerciseAttemptDomain.from_model(att, exercise_domain=exercise)

    summary = attempt.summary()

    # Enrich with student class info if available
    student_class = ""
    student_name = getattr(att.student, "username", "") if att.student else ""
    profile = getattr(att.student, "profile", None)
    if profile:
        meta = profile.metadata or {}
        student_class = getattr(profile, "class_name", "") or meta.get("class_name", "") or ""
        student_name = getattr(profile, "display_name", "") or student_name

    # Get show_answers setting from ExerciseSettings
    show_answers = 'always'  # default
    can_show_answers = True
    try:
        settings = att.exercise.settings
        show_answers = getattr(settings, 'show_answers', 'always')
        end_at = getattr(settings, 'end_at', None)
        time_limit_seconds = getattr(settings, 'time_limit_seconds', None)
        
        from django.utils import timezone
        
        if show_answers == 'never':
            can_show_answers = False
        elif show_answers == 'after_duration':
            # Chỉ hiển thị sau khi hết thời gian làm bài (started_at + duration)
            if att.started_at and time_limit_seconds:
                from datetime import timedelta
                deadline = att.started_at + timedelta(seconds=time_limit_seconds)
                if timezone.now() < deadline:
                    can_show_answers = False
                else:
                    can_show_answers = True
            else:
                # Không có time limit, cho xem luôn
                can_show_answers = True
        elif show_answers == 'after_end':
            # Chỉ hiển thị sau khi hết hạn bài thi (end_at)
            if end_at and timezone.now() < end_at:
                can_show_answers = False
            else:
                can_show_answers = True
    except Exception:
        pass  # No settings, default to always show

    summary.update({
        "student_class": student_class,
        "class_name": student_class,
        "class_code": student_class,
        "student": {
            "id": str(att.student_id) if att.student_id else None,
            "name": student_name or getattr(att.student, "username", "") if att.student else "",
            "class_name": student_class,
            "class_code": student_class,
        },
        "show_answers": show_answers,
        "can_show_answers": can_show_answers,
    })
    return summary


def manual_grade_answer(
    attempt_id: str,
    question_id: str,
    grader_user,
    score: float,
    comment: Optional[str] = None
) -> ExerciseAnswerDomain:
    """
    Manual grading for a given answer.

    Behaviour:
    - Only the course owner or an admin can manual-grade.
    - Finds the ExerciseAnswerModel for (attempt, question).
    - Writes `manual_score` and optionally `grader_comment` into answer JSON,
      also sets answer['score'] = manual_score to override automated score.
    - Sets `correct` flag based on max_points (if provided) or score > 0 rule.
    - Recomputes attempt total by summing per-answer raw points:
        order of precedence for each answer: manual_score -> stored score -> recompute via QuestionDomain
    - Converts raw total to percentage using exercise.total_possible_points().
    - Persists updated answer(s) and attempt.score.
    - Returns ExerciseAnswerDomain for the answer that was manually graded.
    """
    # Load attempt + answer
    try:
        att_model = ExerciseAttemptModel.objects.select_related(
            "exercise__settings", "exercise__lesson__module__course"
        ).prefetch_related("answers__question").get(id=attempt_id)
    except ExerciseAttemptModel.DoesNotExist:
        raise NotFoundError("Attempt not found")

    if not can_manage_exercise(grader_user, att_model.exercise):
        raise PermissionDenied("Không được phép chấm bài kiểm tra này.")

    try:
        answer_model = ExerciseAnswerModel.objects.get(attempt=att_model, question_id=question_id)
    except ExerciseAnswerModel.DoesNotExist:
        raise NotFoundError("Answer not found for grading.")

    # Update answer JSON with manual score and comment, persist
    answer_data = answer_model.answer if isinstance(answer_model.answer, dict) else (answer_model.answer or {})
    answer_data = dict(answer_data)  # defensive copy
    answer_data['manual_score'] = float(score)
    # Optionally store max_points if not present (not overriding)
    # answer_data.setdefault('max_points', answer_data.get('max_points'))
    if comment:
        answer_data['grader_comment'] = comment
    # Make manual score the authoritative stored score
    answer_data['score'] = float(score)

    # Determine correct flag using max_points if available, else score > 0
    max_points = answer_data.get('max_points')
    if max_points is not None:
        try:
            correct_flag = float(score) >= float(max_points)
        except Exception:
            correct_flag = float(score) > 0
    else:
        correct_flag = float(score) > 0

    answer_model.answer = answer_data
    answer_model.correct = bool(correct_flag)
    answer_model.save()

    # Recompute attempt total (raw points) by iterating all answers for this attempt
    total_obtained = 0.0
    # For answers without score we will compute using QuestionDomain.score_answer(...)
    for ans in att_model.answers.all():
        payload = ans.answer or {}
        # payload may be non-dict depending on your model; ensure dict
        if not isinstance(payload, dict):
            payload = {}
        s = None
        if 'manual_score' in payload:
            try:
                s = float(payload['manual_score'])
            except Exception:
                s = 0.0
        elif 'score' in payload:
            try:
                s = float(payload['score'])
            except Exception:
                s = None

        if s is None:
            # compute using question domain (automated scoring)
            try:
                question_dom = QuestionDomain.from_model(ans.question)
                result = question_dom.score_answer(payload)
                s = float(result.get('score', 0.0))
                # persist computed score and correctness for audit
                payload['score'] = s
                ans.answer = payload
                ans.correct = bool(result.get('correct', False))
                ans.save()
            except Exception:
                # fallback
                s = 0.0

        total_obtained += s

    # Convert total raw points -> percentage based on exercise total points
    exercise_domain = ExerciseDomain.from_model(att_model.exercise)
    exercise_total_points = exercise_domain.total_possible_points()
    if exercise_total_points and exercise_total_points > 0:
        new_pct = round((total_obtained / exercise_total_points) * 100.0, 2)
    else:
        # If no per-question points defined, keep raw total
        new_pct = round(total_obtained, 2)

    # Persist attempt score
    att_model.score = new_pct
    att_model.save()

    # Return domain object for the manually graded answer
    return ExerciseAnswerDomain(
        id=str(answer_model.id),
        attempt_id=str(att_model.id),
        question_id=str(question_id),
        answer=answer_model.answer,
        correct=answer_model.correct,
        score=answer_model.answer.get('manual_score', None) if isinstance(answer_model.answer, dict) else None
    )
