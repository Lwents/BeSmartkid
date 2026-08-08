import pytest
from rest_framework.test import APIClient

from content.models import Course, Enrollment
from custom_account.models import UserModel


def _user(username, role):
    return UserModel.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="QaPass1234",
        role=role,
    )


@pytest.mark.django_db
def test_teacher_feedback_uses_message_only_and_supports_history():
    teacher = _user("feedback-teacher", "instructor")
    student = _user("feedback-student", "student")
    course = Course.objects.create(
        title="Khóa phản hồi", owner=teacher, published=True
    )
    Enrollment.objects.create(course=course, student=student)
    client = APIClient()
    client.force_authenticate(teacher)

    created = client.post(
        "/api/teacher/students/feedback/",
        {
            "studentId": student.id,
            "courseId": str(course.id),
            "message": "Em học tốt",
        },
        format="json",
    )
    assert created.status_code == 201
    assert "rating" not in created.data

    legacy_created = client.post(
        "/api/teacher/students/feedback/",
        {
            "studentId": student.id,
            "courseId": str(course.id),
            "message": "Tiếp tục phát huy",
            "rating": 99,
        },
        format="json",
    )
    assert legacy_created.status_code == 201
    assert "rating" not in legacy_created.data

    history = client.get("/api/teacher/students/feedback/")
    assert history.status_code == 200
    assert len(history.data["items"]) == 2
    assert all("rating" not in item for item in history.data["items"])
