import pytest
from rest_framework.test import APIClient

from activities.models import LessonQuestion, Notification
from content.models import Course, Lesson, Module, Subject
from custom_account.models import UserModel


def create_user(username, role, *, is_staff=False):
    return UserModel.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="password123",
        role=role,
        is_staff=is_staff,
    )


def create_lesson(owner, slug):
    subject = Subject.objects.create(title=f"Môn {slug}", slug=slug)
    course = Course.objects.create(
        subject=subject,
        title=f"Khóa {slug}",
        owner=owner,
        published=True,
    )
    module = Module.objects.create(course=course, title="Chương 1", position=1)
    return Lesson.objects.create(
        module=module,
        title="Bài 1",
        position=1,
        published=True,
    )


@pytest.mark.django_db
def test_student_question_notifies_only_course_teacher():
    teacher = create_user("qa-teacher", "instructor")
    admin = create_user("qa-admin", "admin", is_staff=True)
    student = create_user("qa-student", "student")
    lesson = create_lesson(teacher, "qa-teacher-course")
    client = APIClient()
    client.force_authenticate(student)

    response = client.post(
        "/api/student/lesson-questions/",
        {"lesson_id": str(lesson.id), "content": "Em cần thầy giải thích"},
        format="json",
        HTTP_HOST="localhost",
    )

    assert response.status_code == 201
    assert Notification.objects.filter(
        user=teacher,
        category="lesson_question",
    ).count() == 1
    assert not Notification.objects.filter(
        user=admin,
        category__in=("lesson_question", "lesson_question_reply"),
    ).exists()


@pytest.mark.django_db
def test_admin_course_owner_is_not_treated_as_teacher():
    admin = create_user("owner-admin", "admin", is_staff=True)
    student = create_user("owner-student", "student")
    lesson = create_lesson(admin, "admin-owned-course")
    client = APIClient()
    client.force_authenticate(student)

    response = client.post(
        "/api/student/lesson-questions/",
        {"lesson_id": str(lesson.id), "content": "Câu hỏi không gửi cho admin"},
        format="json",
        HTTP_HOST="localhost",
    )

    assert response.status_code == 400
    assert "giáo viên phụ trách" in response.data["detail"]
    assert not LessonQuestion.objects.exists()
    assert not Notification.objects.filter(
        user=admin,
        category__in=("lesson_question", "lesson_question_reply"),
    ).exists()
