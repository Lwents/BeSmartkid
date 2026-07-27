import pytest
from rest_framework.test import APIClient

from activities.models import Exercise, ExerciseAttempt, ExerciseSettings
from content.models import Course, Enrollment, Lesson, Module, Subject
from custom_account.models import UserModel


@pytest.mark.django_db
def test_teacher_student_average_uses_only_owned_course_exams():
    teacher = UserModel.objects.create_user(
        username="student-list-teacher",
        email="student-list-teacher@example.com",
        password="password123",
        role="instructor",
    )
    other_teacher = UserModel.objects.create_user(
        username="student-list-other-teacher",
        email="student-list-other-teacher@example.com",
        password="password123",
        role="instructor",
    )
    student = UserModel.objects.create_user(
        username="student-list-student",
        email="student-list-student@example.com",
        password="password123",
        role="student",
    )
    subject = Subject.objects.create(title="Math scores", slug="math-scores-test")
    course = Course.objects.create(subject=subject, title="Owned course", owner=teacher)
    other_course = Course.objects.create(
        subject=subject,
        title="Other course",
        owner=other_teacher,
    )
    Enrollment.objects.create(course=course, student=student)
    module = Module.objects.create(course=course, title="Owned module", position=1)
    lesson = Lesson.objects.create(module=module, title="Owned lesson", position=1)
    owned_exam = Exercise.objects.create(lesson=lesson, title="Owned exam", type="mcq")
    ExerciseAttempt.objects.create(exercise=owned_exam, student=student, score=60)

    standalone_exam = Exercise.objects.create(title="Standalone exam", type="mcq")
    ExerciseSettings.objects.create(exercise=standalone_exam, course_id=course.id)
    ExerciseAttempt.objects.create(exercise=standalone_exam, student=student, score=100)

    other_module = Module.objects.create(
        course=other_course,
        title="Other module",
        position=1,
    )
    other_lesson = Lesson.objects.create(
        module=other_module,
        title="Other lesson",
        position=1,
    )
    other_exam = Exercise.objects.create(lesson=other_lesson, title="Other exam", type="mcq")
    ExerciseAttempt.objects.create(exercise=other_exam, student=student, score=10)

    client = APIClient()
    client.force_authenticate(teacher)
    response = client.get("/api/teacher/students/", HTTP_HOST="localhost")

    assert response.status_code == 200
    assert response.data["total"] == 1
    assert response.data["items"][0]["avgScore"] == 80.0
