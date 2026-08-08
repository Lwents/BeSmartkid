import pytest
from rest_framework.test import APIClient

from activities.models import Notification
from content.models import Course, Enrollment, Lesson, Module, Subject
from custom_account.models import UserModel


def _user(username, role, *, is_staff=False):
    return UserModel.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="password123",
        role=role,
        is_staff=is_staff,
    )


def _client(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def _exam_payload(course, *, published=False):
    return {
        "title": "[E2E] Kiểm tra phép cộng",
        "type": "mcq",
        "published": published,
        "settings": {
            "course_id": str(course.id),
            "duration_seconds": 900,
            "pass_score": 50,
            "max_attempts": 2,
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


@pytest.mark.django_db
def test_teacher_student_learning_flow_is_scoped_and_connected():
    teacher = _user("e2e-teacher", "instructor")
    other_teacher = _user("e2e-other-teacher", "instructor")
    admin = _user("e2e-admin", "admin", is_staff=True)
    student = _user("e2e-student", "student")
    outsider = _user("e2e-outsider", "student")

    subject = Subject.objects.create(title="Toán E2E", slug="toan-e2e")
    course = Course.objects.create(
        subject=subject,
        title="[E2E] Toán lớp 4",
        grade="4",
        owner=teacher,
        published=True,
    )
    Enrollment.objects.create(course=course, student=student)
    module = Module.objects.create(course=course, title="Chương 1", position=1)
    first_lesson = Lesson.objects.create(
        module=module,
        title="Bài 1: Phép cộng",
        content_type="text",
        text_content="Hai cộng ba bằng năm.",
        position=1,
        published=True,
    )
    second_lesson = Lesson.objects.create(
        module=module,
        title="Bài 2: Luyện tập",
        content_type="text",
        text_content="Luyện tập phép cộng.",
        position=2,
        published=True,
    )

    teacher_client = _client(teacher)
    other_teacher_client = _client(other_teacher)
    student_client = _client(student)
    outsider_client = _client(outsider)

    assert student_client.get(
        f"/api/student/courses/{course.id}/player/{second_lesson.id}/",
        HTTP_HOST="localhost",
    ).status_code == 403
    complete_response = student_client.post(
        f"/api/content/lessons/{first_lesson.id}/progress/",
        {"video_watched": True},
        format="json",
        HTTP_HOST="localhost",
    )
    assert complete_response.status_code == 200
    assert complete_response.data["completed"] is True
    assert student_client.get(
        f"/api/student/courses/{course.id}/player/{second_lesson.id}/",
        HTTP_HOST="localhost",
    ).status_code == 200
    assert outsider_client.get(
        f"/api/student/courses/{course.id}/player/{first_lesson.id}/",
        HTTP_HOST="localhost",
    ).status_code == 403
    assert outsider_client.post(
        f"/api/content/lessons/{first_lesson.id}/progress/",
        {"video_watched": True},
        format="json",
        HTTP_HOST="localhost",
    ).status_code == 403
    assert outsider_client.post(
        "/api/student/lesson-questions/",
        {
            "lesson_id": str(first_lesson.id),
            "content": "Câu hỏi từ học sinh ngoài khóa",
        },
        format="json",
        HTTP_HOST="localhost",
    ).status_code == 403

    question_response = student_client.post(
        "/api/student/lesson-questions/",
        {
            "lesson_id": str(first_lesson.id),
            "content": "Thầy cô giải thích phép cộng giúp em với ạ.",
        },
        format="json",
        HTTP_HOST="localhost",
    )
    assert question_response.status_code == 201
    question_id = question_response.data["id"]
    assert Notification.objects.filter(
        user=teacher,
        category="lesson_question",
    ).count() == 1
    assert not Notification.objects.filter(
        user=admin,
        category="lesson_question",
    ).exists()

    teacher_questions = teacher_client.get(
        "/api/teacher/lesson-questions/",
        HTTP_HOST="localhost",
    )
    other_teacher_questions = other_teacher_client.get(
        "/api/teacher/lesson-questions/",
        HTTP_HOST="localhost",
    )
    assert teacher_questions.status_code == 200
    assert [item["id"] for item in teacher_questions.data["items"]] == [question_id]
    assert other_teacher_questions.status_code == 200
    assert other_teacher_questions.data["items"] == []

    reply_response = teacher_client.post(
        f"/api/teacher/lesson-questions/{question_id}/reply/",
        {"content": "Em đặt các số thẳng cột rồi cộng từ phải sang trái nhé."},
        format="json",
        HTTP_HOST="localhost",
    )
    assert reply_response.status_code == 201
    assert Notification.objects.filter(
        user=student,
        category="lesson_question_reply",
        metadata__lesson_id=str(first_lesson.id),
    ).count() == 1

    draft_response = teacher_client.post(
        "/api/activities/exercises/",
        _exam_payload(course),
        format="json",
        HTTP_HOST="localhost",
    )
    assert draft_response.status_code == 201
    exam_id = draft_response.data["id"]
    question = draft_response.data["questions"][0]
    correct_choice = next(choice for choice in question["choices"] if choice["is_correct"])

    student_draft_list = student_client.get(
        "/api/student/exams/",
        HTTP_HOST="localhost",
    )
    assert student_draft_list.status_code == 200
    assert exam_id not in {item["id"] for item in student_draft_list.data}
    assert student_client.get(
        f"/api/student/exams/{exam_id}/",
        HTTP_HOST="localhost",
    ).status_code in (403, 404)
    student_activity_list = student_client.get(
        "/api/activities/exercises/",
        HTTP_HOST="localhost",
    )
    assert exam_id not in {item["id"] for item in student_activity_list.data}
    assert not Notification.objects.filter(category="exam").exists()

    forbidden_edit = other_teacher_client.patch(
        f"/api/activities/exercises/{exam_id}/",
        {"published": True},
        format="json",
        HTTP_HOST="localhost",
    )
    assert forbidden_edit.status_code in (403, 404)
    assert other_teacher_client.post(
        f"/api/activities/exercises/{exam_id}/questions/",
        {"prompt": "Câu hỏi không được phép", "meta": {"type": "mcq"}},
        format="json",
        HTTP_HOST="localhost",
    ).status_code == 403
    assert other_teacher_client.delete(
        f"/api/activities/choices/{correct_choice['id']}/",
        HTTP_HOST="localhost",
    ).status_code == 403

    publish_response = teacher_client.patch(
        f"/api/activities/exercises/{exam_id}/",
        {"published": True},
        format="json",
        HTTP_HOST="localhost",
    )
    assert publish_response.status_code == 200
    assert Notification.objects.filter(
        user=student,
        category="exam",
        metadata__exam_id=exam_id,
    ).count() == 1
    assert not Notification.objects.filter(user=outsider, category="exam").exists()

    student_exam_list = student_client.get(
        "/api/student/exams/",
        HTTP_HOST="localhost",
    )
    outsider_exam_list = outsider_client.get(
        "/api/student/exams/",
        HTTP_HOST="localhost",
    )
    assert exam_id in {item["id"] for item in student_exam_list.data}
    assert exam_id not in {item["id"] for item in outsider_exam_list.data}
    assert exam_id in {
        item["id"] for item in student_client.get(
            "/api/activities/exercises/", HTTP_HOST="localhost"
        ).data
    }
    assert exam_id not in {
        item["id"] for item in other_teacher_client.get(
            "/api/activities/exercises/", HTTP_HOST="localhost"
        ).data
    }
    assert outsider_client.get(
        f"/api/activities/exercises/{exam_id}/",
        HTTP_HOST="localhost",
    ).status_code == 403
    assert outsider_client.get(
        f"/api/student/exams/{exam_id}/",
        HTTP_HOST="localhost",
    ).status_code in (403, 404)
    assert outsider_client.post(
        f"/api/student/exams/{exam_id}/start/",
        {},
        format="json",
        HTTP_HOST="localhost",
    ).status_code == 403

    detail_response = student_client.get(
        f"/api/student/exams/{exam_id}/",
        HTTP_HOST="localhost",
    )
    assert detail_response.status_code == 200
    assert all(
        "is_correct" not in choice
        for item in detail_response.data["questions"]
        for choice in item["choices"]
    )
    start_response = student_client.post(
        f"/api/student/exams/{exam_id}/start/",
        {},
        format="json",
        HTTP_HOST="localhost",
    )
    assert start_response.status_code == 201
    attempt_id = start_response.data["id"]
    assert outsider_client.post(
        f"/api/activities/attempts/{attempt_id}/finalize/",
        {},
        format="json",
        HTTP_HOST="localhost",
    ).status_code == 403
    assert outsider_client.get(
        f"/api/activities/attempts/{attempt_id}/",
        HTTP_HOST="localhost",
    ).status_code == 403
    submit_response = student_client.post(
        f"/api/student/exams/{exam_id}/submit/{attempt_id}/",
        {
            "answers": {
                question["id"]: {"selected_choice_id": correct_choice["id"]},
            },
        },
        format="json",
        HTTP_HOST="localhost",
    )
    assert submit_response.status_code == 200
    assert submit_response.data["score"] == 100.0
    assert submit_response.data["passed"] is True
    assert other_teacher_client.post(
        f"/api/activities/attempts/{attempt_id}/grade/",
        {"question_id": question["id"], "score": 0},
        format="json",
        HTTP_HOST="localhost",
    ).status_code == 403
    owner_grade_response = teacher_client.post(
        f"/api/activities/attempts/{attempt_id}/grade/",
        {"question_id": question["id"], "score": 1},
        format="json",
        HTTP_HOST="localhost",
    )
    assert owner_grade_response.status_code == 200
    assert outsider_client.get(
        f"/api/student/exams/{exam_id}/result/{attempt_id}/",
        HTTP_HOST="localhost",
    ).status_code in (403, 404)

    owner_stats = teacher_client.get(
        f"/api/activities/exercises/{exam_id}/stats/",
        HTTP_HOST="localhost",
    )
    owner_attempts = teacher_client.get(
        f"/api/activities/exercises/{exam_id}/attempts/",
        HTTP_HOST="localhost",
    )
    assert owner_stats.status_code == 200
    assert owner_attempts.status_code == 200
    assert len(owner_attempts.data) == 1
    assert owner_attempts.data[0]["student_id"] == str(student.id)
    assert other_teacher_client.get(
        f"/api/activities/exercises/{exam_id}/attempts/",
        HTTP_HOST="localhost",
    ).status_code in (403, 404)
    assert other_teacher_client.get(
        f"/api/activities/exercises/{exam_id}/stats/",
        HTTP_HOST="localhost",
    ).status_code in (403, 404)
    assert other_teacher_client.get(
        f"/api/activities/exercises/{exam_id}/export/",
        HTTP_HOST="localhost",
    ).status_code in (403, 404)

    duplicate_response = teacher_client.patch(
        f"/api/activities/exercises/{exam_id}/",
        {"title": "[E2E] Kiểm tra phép cộng đã sửa"},
        format="json",
        HTTP_HOST="localhost",
    )
    assert duplicate_response.status_code == 200
    assert Notification.objects.filter(
        user=student,
        category="exam",
        metadata__exam_id=exam_id,
    ).count() == 1

    unpublish_response = teacher_client.patch(
        f"/api/activities/exercises/{exam_id}/",
        {"published": False},
        format="json",
        HTTP_HOST="localhost",
    )
    assert unpublish_response.status_code == 200
    assert exam_id not in {
        item["id"] for item in student_client.get(
            "/api/student/exams/", HTTP_HOST="localhost"
        ).data
    }
    assert student_client.post(
        f"/api/student/exams/{exam_id}/start/",
        {},
        format="json",
        HTTP_HOST="localhost",
    ).status_code == 403

    teacher_report = teacher_client.get(
        "/api/activities/exercises/?include_stats=true",
        HTTP_HOST="localhost",
    )
    assert teacher_report.status_code == 200
    closed_exam = next(item for item in teacher_report.data if item["id"] == exam_id)
    assert closed_exam["published"] is False
    assert closed_exam["submissions"] == 1
    assert closed_exam["status"] == "closed"

    notifications_response = student_client.get(
        "/api/student/notifications/",
        HTTP_HOST="localhost",
    )
    assert notifications_response.status_code == 200
    exam_notification = next(
        item for item in notifications_response.data["notifications"]
        if item["category"] == "exam"
    )
    assert exam_notification["metadata"]["course_id"] == str(course.id)
    assert student_client.patch(
        f"/api/student/notifications/{exam_notification['id']}/read/",
        {},
        format="json",
        HTTP_HOST="localhost",
    ).status_code == 200

    Notification.objects.create(
        user=student,
        title="[E2E] Thông báo chưa đọc",
        message="Dùng để kiểm tra đánh dấu tất cả.",
        category="system",
    )
    outsider_notification = Notification.objects.create(
        user=outsider,
        title="[E2E] Thông báo của tài khoản khác",
        message="Không được thay đổi khi học sinh hiện tại đọc tất cả.",
        category="system",
    )
    assert student_client.patch(
        "/api/student/notifications/read-all/",
        {},
        format="json",
        HTTP_HOST="localhost",
    ).status_code == 200
    assert not Notification.objects.filter(user=student, is_read=False).exists()
    outsider_notification.refresh_from_db()
    assert outsider_notification.is_read is False

    dashboard_response = teacher_client.get(
        "/api/teacher/dashboard/",
        HTTP_HOST="localhost",
    )
    assert dashboard_response.status_code == 200
    assert dashboard_response.data["stats"]["attempts"] == 1
