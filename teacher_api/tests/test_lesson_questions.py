import pytest
from rest_framework.test import APIClient

from activities.models import LessonQuestion, LessonQuestionReply, Notification
from content.models import Course, Lesson, Module, Subject
from custom_account.models import UserModel


@pytest.fixture
def lesson_question_data(db):
    owner = UserModel.objects.create_user(
        username="question-owner",
        email="question-owner@example.com",
        password="password123",
        role="instructor",
    )
    other_teacher = UserModel.objects.create_user(
        username="question-other-teacher",
        email="question-other-teacher@example.com",
        password="password123",
        role="instructor",
    )
    student = UserModel.objects.create_user(
        username="question-student",
        email="question-student@example.com",
        password="password123",
        role="student",
    )
    subject = Subject.objects.create(title="Toán hỏi đáp", slug="toan-hoi-dap-test")
    course = Course.objects.create(
        subject=subject,
        title="Khóa học hỏi đáp",
        owner=owner,
        published=True,
    )
    module = Module.objects.create(course=course, title="Chương hỏi đáp", position=1)
    lesson = Lesson.objects.create(
        module=module,
        title="Bài học hỏi đáp",
        position=1,
        published=True,
    )
    question = LessonQuestion.objects.create(
        lesson=lesson,
        student=student,
        content="Em chưa hiểu phần này",
    )
    return owner, other_teacher, student, question


@pytest.mark.django_db
def test_teacher_only_sees_questions_from_owned_courses(lesson_question_data):
    owner, other_teacher, _, question = lesson_question_data
    client = APIClient()

    client.force_authenticate(owner)
    owner_response = client.get("/api/teacher/lesson-questions/", HTTP_HOST="localhost")

    client.force_authenticate(other_teacher)
    other_response = client.get("/api/teacher/lesson-questions/", HTTP_HOST="localhost")
    forbidden_reply = client.post(
        f"/api/teacher/lesson-questions/{question.id}/reply/",
        {"content": "Câu trả lời không được phép"},
        format="json",
        HTTP_HOST="localhost",
    )

    assert owner_response.status_code == 200
    assert [item["id"] for item in owner_response.data["items"]] == [str(question.id)]
    assert other_response.status_code == 200
    assert other_response.data["items"] == []
    assert forbidden_reply.status_code == 404
    assert not LessonQuestionReply.objects.exists()


@pytest.mark.django_db
def test_course_owner_can_reply_and_student_is_notified(lesson_question_data):
    owner, _, student, question = lesson_question_data
    client = APIClient()
    client.force_authenticate(owner)

    response = client.post(
        f"/api/teacher/lesson-questions/{question.id}/reply/",
        {"content": "Giáo viên giải thích phần này cho em nhé."},
        format="json",
        HTTP_HOST="localhost",
    )

    assert response.status_code == 201
    assert response.data["item"]["student_name"] == student.get_full_name()
    replies = response.data["item"]["replies"]
    assert len(replies) == 1
    assert replies[0]["is_teacher"] is True
    assert replies[0]["user_name"] == owner.get_full_name()
    assert replies[0]["content"] == "Giáo viên giải thích phần này cho em nhé."
    assert Notification.objects.filter(
        user=student,
        category="lesson_question_reply",
        title="Thầy cô đã trả lời em",
        metadata__lesson_question_id=str(question.id),
        metadata__course_title="Khóa học hỏi đáp",
        metadata__lesson_title="Bài học hỏi đáp",
    ).exists()
