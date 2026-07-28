import pytest
from rest_framework.test import APIClient

from activities.models import LessonQuestion, LessonQuestionReply, LessonQuestionReport
from content.models import Course, Enrollment, Lesson, Module
from custom_account.models import UserModel


def _user(username, role):
    return UserModel.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="QaPass1234",
        role=role,
    )


@pytest.mark.django_db
def test_student_outside_course_cannot_interact_with_lesson_discussion():
    teacher = _user("discussion-teacher", "instructor")
    enrolled_student = _user("discussion-owner", "student")
    outsider = _user("discussion-outsider", "student")
    course = Course.objects.create(
        title="Khóa hỏi đáp", owner=teacher, published=True
    )
    Enrollment.objects.create(course=course, student=enrolled_student)
    module = Module.objects.create(course=course, title="Chương 1", position=0)
    lesson = Lesson.objects.create(
        module=module, title="Bài 1", position=0, published=True
    )
    question = LessonQuestion.objects.create(
        lesson=lesson, student=enrolled_student, content="Em chưa hiểu"
    )
    reply = LessonQuestionReply.objects.create(
        question=question,
        user=teacher,
        content="Thầy giải thích nhé",
        is_teacher=True,
    )

    client = APIClient()
    client.force_authenticate(outsider)

    assert client.post(
        f"/api/student/lesson-questions/{question.id}/reply/",
        {"content": "Trả lời trái phép"},
        format="json",
    ).status_code == 403
    assert client.post(
        f"/api/student/lesson-questions/{question.id}/react/",
        {},
        format="json",
    ).status_code == 403
    assert client.post(
        f"/api/student/lesson-question-replies/{reply.id}/react/",
        {},
        format="json",
    ).status_code == 403
    assert client.post(
        "/api/student/lesson-question-report/",
        {"question_id": str(question.id), "reason": "Không thích"},
        format="json",
    ).status_code == 403

    assert not question.replies.filter(user=outsider).exists()
    assert not LessonQuestionReport.objects.filter(reporter=outsider).exists()


@pytest.mark.django_db
def test_enrolled_student_can_reply_and_react_to_accessible_discussion():
    teacher = _user("discussion-teacher-ok", "instructor")
    student = _user("discussion-student-ok", "student")
    course = Course.objects.create(
        title="Khóa hỏi đáp hợp lệ", owner=teacher, published=True
    )
    Enrollment.objects.create(course=course, student=student)
    module = Module.objects.create(course=course, title="Chương 1", position=0)
    lesson = Lesson.objects.create(
        module=module, title="Bài 1", position=0, published=True
    )
    question = LessonQuestion.objects.create(
        lesson=lesson, student=student, content="Câu hỏi hợp lệ"
    )

    client = APIClient()
    client.force_authenticate(student)
    response = client.post(
        f"/api/student/lesson-questions/{question.id}/reply/",
        {"content": "Em bổ sung câu hỏi"},
        format="json",
    )
    assert response.status_code == 201

    reaction = client.post(
        f"/api/student/lesson-questions/{question.id}/react/",
        {},
        format="json",
    )
    assert reaction.status_code == 200
    assert reaction.data["reacted"] is True
