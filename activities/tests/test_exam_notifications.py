import pytest
from rest_framework.test import APIClient

from activities.models import Notification
from content.models import Course, Enrollment, Subject
from custom_account.models import UserModel


def _exercise_payload(course, published):
    return {
        "title": "Kiểm tra phép cộng",
        "type": "mcq",
        "published": published,
        "settings": {
            "course_id": str(course.id),
            "duration_seconds": 900,
            "pass_score": 50,
        },
        "questions": [{
            "prompt": "Hai cộng ba bằng bao nhiêu?",
            "meta": {"type": "mcq", "points": 1},
            "choices": [
                {"text": "5", "is_correct": True, "position": 0},
                {"text": "4", "is_correct": False, "position": 1},
            ],
        }],
    }


@pytest.fixture
def exam_notification_data(db):
    teacher = UserModel.objects.create_user(
        username="exam-notification-teacher",
        email="exam-notification-teacher@example.com",
        password="password123",
        role="instructor",
    )
    first_student = UserModel.objects.create_user(
        username="exam-notification-student-1",
        email="exam-notification-student-1@example.com",
        password="password123",
        role="student",
    )
    second_student = UserModel.objects.create_user(
        username="exam-notification-student-2",
        email="exam-notification-student-2@example.com",
        password="password123",
        role="student",
    )
    outsider = UserModel.objects.create_user(
        username="exam-notification-outsider",
        email="exam-notification-outsider@example.com",
        password="password123",
        role="student",
    )
    subject = Subject.objects.create(title="Toán thông báo", slug="toan-thong-bao-test")
    course = Course.objects.create(
        subject=subject,
        title="Toán lớp 4",
        owner=teacher,
        published=True,
    )
    Enrollment.objects.create(course=course, student=first_student)
    Enrollment.objects.create(course=course, student=second_student)
    return teacher, first_student, second_student, outsider, course


@pytest.mark.django_db
def test_published_exam_notifies_only_enrolled_students_once(exam_notification_data):
    teacher, first_student, second_student, outsider, course = exam_notification_data
    client = APIClient()
    client.force_authenticate(teacher)

    response = client.post(
        "/api/activities/exercises/",
        _exercise_payload(course, published=True),
        format="json",
        HTTP_HOST="localhost",
    )

    assert response.status_code == 201
    exam_id = response.data["id"]
    notifications = Notification.objects.filter(category="exam")
    assert set(notifications.values_list("user_id", flat=True)) == {
        first_student.id,
        second_student.id,
    }
    assert not notifications.filter(user=outsider).exists()
    assert all(item.title == "Có bài kiểm tra mới" for item in notifications)
    assert all(item.metadata["exam_id"] == exam_id for item in notifications)
    assert all(item.metadata["course_id"] == str(course.id) for item in notifications)

    student_client = APIClient()
    student_client.force_authenticate(first_student)
    list_response = student_client.get(
        "/api/student/notifications/",
        HTTP_HOST="localhost",
    )
    assert list_response.status_code == 200
    student_notification = list_response.data["notifications"][0]
    assert student_notification["category"] == "exam"
    assert student_notification["metadata"]["exam_id"] == exam_id
    assert student_notification["metadata"]["course_id"] == str(course.id)

    edit_response = client.patch(
        f"/api/activities/exercises/{exam_id}/",
        {"title": "Kiểm tra phép cộng đã sửa"},
        format="json",
        HTTP_HOST="localhost",
    )

    assert edit_response.status_code == 200
    assert Notification.objects.filter(category="exam").count() == 2


@pytest.mark.django_db
def test_draft_exam_notifies_students_when_first_published(exam_notification_data):
    teacher, first_student, second_student, _, course = exam_notification_data
    client = APIClient()
    client.force_authenticate(teacher)
    create_response = client.post(
        "/api/activities/exercises/",
        _exercise_payload(course, published=False),
        format="json",
        HTTP_HOST="localhost",
    )

    assert create_response.status_code == 201
    assert not Notification.objects.filter(category="exam").exists()

    exam_id = create_response.data["id"]
    publish_response = client.patch(
        f"/api/activities/exercises/{exam_id}/",
        {"published": True},
        format="json",
        HTTP_HOST="localhost",
    )

    assert publish_response.status_code == 200
    assert set(Notification.objects.filter(category="exam").values_list(
        "user_id", flat=True
    )) == {first_student.id, second_student.id}
