from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from activities.models import (
    Choice,
    Exercise,
    ExerciseAnswer,
    ExerciseAttempt,
    ExerciseSettings,
    Question,
)
from content.models import Course, Enrollment
from custom_account.models import UserModel


def _user(username, role):
    return UserModel.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="QaPass1234",
        role=role,
    )


def _exam_fixture(*, pass_score=60, max_attempts=2):
    teacher = _user(f"timing-teacher-{pass_score}", "instructor")
    student = _user(f"timing-student-{pass_score}", "student")
    course = Course.objects.create(
        title=f"Khóa thi {pass_score}", owner=teacher, published=True, grade="4"
    )
    Enrollment.objects.create(course=course, student=student)
    exercise = Exercise.objects.create(
        title=f"Đề thi {pass_score}", type="mcq", published=True
    )
    ExerciseSettings.objects.create(
        exercise=exercise,
        course_id=course.id,
        time_limit_seconds=600,
        max_attempts=max_attempts,
        pass_score=pass_score,
    )
    question = Question.objects.create(
        exercise=exercise, prompt="1 + 1 = ?", meta={"type": "mcq", "points": 1}
    )
    Choice.objects.create(question=question, text="2", is_correct=True, position=0)
    return student, exercise, question


@pytest.mark.django_db
def test_reopening_attempt_keeps_original_deadline_and_expired_attempt_is_closed():
    student, exercise, _ = _exam_fixture()
    client = APIClient()
    client.force_authenticate(student)

    started = client.post(f"/api/student/exams/{exercise.id}/start/", {}, format="json")
    assert started.status_code == 201
    assert started.data["deadlineAt"]
    first_id = started.data["id"]

    attempt = ExerciseAttempt.objects.get(id=first_id)
    original_start = timezone.now() - timedelta(seconds=120)
    ExerciseAttempt.objects.filter(id=attempt.id).update(started_at=original_start)

    resumed = client.post(f"/api/student/exams/{exercise.id}/start/", {}, format="json")
    assert resumed.status_code == 201
    assert resumed.data["id"] == first_id
    resumed_deadline = timezone.datetime.fromisoformat(resumed.data["deadlineAt"])
    assert abs((resumed_deadline - (original_start + timedelta(seconds=600))).total_seconds()) < 1

    expired_start = timezone.now() - timedelta(seconds=700)
    ExerciseAttempt.objects.filter(id=attempt.id).update(started_at=expired_start)
    restarted = client.post(f"/api/student/exams/{exercise.id}/start/", {}, format="json")
    assert restarted.status_code == 201
    assert restarted.data["id"] != first_id
    attempt.refresh_from_db()
    assert attempt.finished_at is not None


@pytest.mark.django_db
def test_exam_detail_exposes_attempt_history_without_internal_ids_in_messages():
    student, exercise, _ = _exam_fixture(pass_score=65)
    end_at = timezone.now() + timedelta(days=2)
    exercise.settings.end_at = end_at
    exercise.settings.save(update_fields=["end_at"])
    ExerciseAttempt.objects.create(
        exercise=exercise,
        student=student,
        finished_at=timezone.now(),
        score=70,
    )
    client = APIClient()
    client.force_authenticate(student)

    response = client.get(f"/api/student/exams/{exercise.id}/")

    assert response.status_code == 200
    assert response.data["attemptsUsed"] == 1
    assert response.data["maxAttempts"] == 2
    assert response.data["attemptsRemaining"] == 1
    assert response.data["lastScore"] == 70.0
    assert response.data["bestScore"] == 70.0
    assert response.data["endAt"] == end_at.isoformat()


@pytest.mark.django_db
def test_certificates_use_exam_pass_score_and_return_one_best_certificate():
    student, exercise, _ = _exam_fixture(pass_score=60)
    ExerciseAttempt.objects.create(
        exercise=exercise, student=student, finished_at=timezone.now(), score=55
    )
    best = ExerciseAttempt.objects.create(
        exercise=exercise, student=student, finished_at=timezone.now(), score=100
    )
    ExerciseAttempt.objects.create(
        exercise=exercise, student=student, finished_at=timezone.now(), score=80
    )

    client = APIClient()
    client.force_authenticate(student)
    response = client.get("/api/student/exams/certificates/")

    assert response.status_code == 200
    rows = [item for item in response.data if item["title"] == f"Chứng chỉ {exercise.title}"]
    assert len(rows) == 1
    assert rows[0]["id"] == str(best.id)
    assert rows[0]["score"] == 100.0


@pytest.mark.django_db
def test_students_with_same_visible_result_share_the_same_rank():
    student, exercise, question = _exam_fixture(pass_score=50)
    other = _user("ranking-tie-student", "student")
    Enrollment.objects.create(course_id=exercise.settings.course_id, student=other)
    choice = question.choices.get(is_correct=True)

    for index, user in enumerate((student, other)):
        attempt = ExerciseAttempt.objects.create(
            exercise=exercise,
            student=user,
            finished_at=timezone.now() + timedelta(seconds=index),
            score=100,
            metadata={"time_taken": 10},
        )
        ExerciseAnswer.objects.create(
            attempt=attempt,
            question=question,
            answer={"selected_choice_id": str(choice.id), "score": 1},
            correct=True,
        )

    client = APIClient()
    client.force_authenticate(student)
    response = client.get(f"/api/student/exams/{exercise.id}/ranking/")

    assert response.status_code == 200
    assert response.data["participants"] == 2
    assert [row["rank"] for row in response.data["top"]] == [1, 1]
