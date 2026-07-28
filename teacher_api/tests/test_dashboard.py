from django.utils import timezone
import pytest
from rest_framework.test import APIClient

from activities.models import Exercise, ExerciseAttempt
from content.models import Course, Enrollment, Lesson, LessonProgress, Module, Subject
from custom_account.models import UserModel


@pytest.mark.django_db
def test_teacher_dashboard_returns_real_activity_rates():
    teacher = UserModel.objects.create_user(
        username="dashboard-teacher",
        email="dashboard-teacher@example.com",
        password="password123",
        role="instructor",
    )
    first_student = UserModel.objects.create_user(
        username="dashboard-student-1",
        email="dashboard-student-1@example.com",
        password="password123",
        role="student",
    )
    second_student = UserModel.objects.create_user(
        username="dashboard-student-2",
        email="dashboard-student-2@example.com",
        password="password123",
        role="student",
    )
    subject = Subject.objects.create(title="Toán dashboard", slug="toan-dashboard-test")
    published_course = Course.objects.create(
        subject=subject,
        title="Khóa đã mở",
        owner=teacher,
        published=True,
    )
    draft_course = Course.objects.create(
        subject=subject,
        title="Khóa bản nháp",
        owner=teacher,
        published=False,
    )
    Enrollment.objects.create(course=published_course, student=first_student)
    Enrollment.objects.create(course=draft_course, student=second_student)
    # Học sinh chưa bắt đầu bài vẫn nằm trong mẫu số tỷ lệ hoàn thành.
    Enrollment.objects.create(course=published_course, student=second_student)

    published_module = Module.objects.create(
        course=published_course, title="Chương đã mở", position=1
    )
    draft_module = Module.objects.create(course=draft_course, title="Chương nháp", position=1)
    completed_lesson = Lesson.objects.create(
        module=published_module,
        title="Bài đã hoàn thành",
        position=1,
        published=True,
    )
    started_lesson = Lesson.objects.create(
        module=draft_module,
        title="Bài đang học",
        position=1,
        published=False,
    )
    LessonProgress.objects.create(
        lesson=completed_lesson,
        student=first_student,
        completed=True,
        completed_at=timezone.now(),
    )
    LessonProgress.objects.create(
        lesson=started_lesson,
        student=first_student,
        completed=False,
    )

    published_exam = Exercise.objects.create(
        lesson=completed_lesson,
        title="Bài thi đã mở",
        type="mcq",
        published=True,
    )
    draft_exam = Exercise.objects.create(
        lesson=started_lesson,
        title="Bài thi nháp",
        type="mcq",
        published=False,
    )
    ExerciseAttempt.objects.create(
        exercise=published_exam,
        student=first_student,
        finished_at=timezone.now(),
        score=80,
    )
    ExerciseAttempt.objects.create(exercise=draft_exam, student=first_student)

    client = APIClient()
    client.force_authenticate(teacher)
    response = client.get("/api/teacher/dashboard/", HTTP_HOST="localhost")

    assert response.status_code == 200
    assert response.data["stats"] == {
        "courses": 2,
        "students": 2,
        "assignments": 2,
        "exams": 2,
        "attempts": 1,
    }
    assert response.data["rates"] == {
        "coursePublished": 50,
        "studentActive": 50,
        "lessonPublished": 50,
        "examPublished": 50,
        "attemptSubmitted": 50,
        "completion": 50,
    }
