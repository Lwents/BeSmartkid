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
def test_teacher_feedback_rejects_rating_outside_zero_to_ten_and_supports_history():
    teacher = _user("feedback-teacher", "instructor")
    student = _user("feedback-student", "student")
    course = Course.objects.create(
        title="Khóa phản hồi", owner=teacher, published=True
    )
    Enrollment.objects.create(course=course, student=student)
    client = APIClient()
    client.force_authenticate(teacher)

    invalid = client.post(
        "/api/teacher/students/feedback/",
        {
            "studentId": student.id,
            "courseId": str(course.id),
            "message": "Em học tốt",
            "rating": 11,
        },
        format="json",
    )
    assert invalid.status_code == 400

    created = client.post(
        "/api/teacher/students/feedback/",
        {
            "studentId": student.id,
            "courseId": str(course.id),
            "message": "Em học tốt",
            "rating": 9,
        },
        format="json",
    )
    assert created.status_code == 201

    history = client.get("/api/teacher/students/feedback/")
    assert history.status_code == 200
    assert len(history.data["items"]) == 1
    assert history.data["items"][0]["rating"] == 9.0
