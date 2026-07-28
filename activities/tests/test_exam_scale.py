import pytest
from rest_framework.test import APIClient

from activities.models import ExerciseAttempt, Notification
from content.models import Course, Enrollment
from custom_account.models import UserModel


pytestmark = pytest.mark.filterwarnings(
    "ignore:datetime.datetime.utcnow.*:DeprecationWarning"
)


def _user(username, role):
    return UserModel.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="QaPass1234",
        role=role,
    )


@pytest.mark.django_db
def test_fifty_ai_questions_and_ten_students_complete_without_data_loss():
    teacher = _user("scale-teacher", "instructor")
    students = [_user(f"scale-student-{index}", "student") for index in range(10)]
    course = Course.objects.create(
        title="Khóa kiểm thử 50 câu",
        owner=teacher,
        grade="4",
        published=True,
    )
    Enrollment.objects.bulk_create([
        Enrollment(course=course, student=student) for student in students
    ])
    questions = []
    for index in range(50):
        questions.append({
            "prompt": f"Câu AI số {index + 1}: {index} + 1 bằng bao nhiêu?",
            "meta": {"type": "mcq", "points": 1},
            "choices": [
                {"text": str(index + 1), "is_correct": True, "position": 0},
                {"text": str(index + 2), "is_correct": False, "position": 1},
            ],
        })

    teacher_client = APIClient()
    teacher_client.force_authenticate(teacher)
    created = teacher_client.post(
        "/api/activities/exercises/",
        {
            "title": "Đề AI 50 câu",
            "type": "mcq",
            "published": True,
            "settings": {
                "course_id": str(course.id),
                "duration_seconds": 3600,
                "pass_score": 80,
                "max_attempts": 1,
            },
            "questions": questions,
        },
        format="json",
        HTTP_HOST="localhost",
    )
    assert created.status_code == 201
    assert len(created.data["questions"]) == 50
    assert Notification.objects.filter(category="exam").count() == 10

    exercise_id = created.data["id"]
    answer_key = {
        question["id"]: {
            "selected_choice_id": next(
                choice["id"] for choice in question["choices"] if choice["is_correct"]
            )
        }
        for question in created.data["questions"]
    }
    for student in students:
        client = APIClient()
        client.force_authenticate(student)
        started = client.post(
            f"/api/student/exams/{exercise_id}/start/",
            {},
            format="json",
            HTTP_HOST="localhost",
        )
        assert started.status_code == 201
        assert len(started.data["questions"]) == 50
        submitted = client.post(
            f"/api/student/exams/{exercise_id}/submit/{started.data['id']}/",
            {"answers": answer_key},
            format="json",
            HTTP_HOST="localhost",
        )
        assert submitted.status_code == 200
        assert submitted.data["score"] == 100.0
        assert submitted.data["correctCount"] == 50
        attempt = ExerciseAttempt.objects.get(id=started.data["id"])
        metadata = dict(attempt.metadata or {})
        metadata["time_taken"] = 10
        ExerciseAttempt.objects.filter(id=attempt.id).update(metadata=metadata)

    ranking_client = APIClient()
    ranking_client.force_authenticate(students[0])
    ranking = ranking_client.get(
        f"/api/student/exams/{exercise_id}/ranking/",
        HTTP_HOST="localhost",
    )
    assert ranking.status_code == 200
    assert ranking.data["participants"] == 10
    assert len(ranking.data["top"]) == 10
    assert {row["rank"] for row in ranking.data["top"]} == {1}
