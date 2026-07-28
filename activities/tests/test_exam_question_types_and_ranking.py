import pytest
from rest_framework.test import APIClient

from content.models import Course, Enrollment, Subject
from custom_account.models import UserModel


def _user(username, role):
    return UserModel.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password=None,
        role=role,
    )


@pytest.mark.django_db
def test_student_exam_preserves_all_question_types_and_returns_useful_ranking():
    teacher = _user("question-types-teacher", "instructor")
    student = _user("question-types-student", "student")
    subject = Subject.objects.create(title="Toán nhiều dạng", slug="toan-nhieu-dang")
    course = Course.objects.create(
        subject=subject,
        title="Khóa kiểm tra nhiều dạng",
        grade="4",
        owner=teacher,
        published=True,
    )
    Enrollment.objects.create(course=course, student=student)
    teacher_client = APIClient()
    teacher_client.force_authenticate(teacher)
    created = teacher_client.post(
        "/api/activities/exercises/",
        {
            "title": "Đề có ba dạng câu hỏi",
            "type": "mcq",
            "published": True,
            "settings": {
                "course_id": str(course.id),
                "duration_seconds": 1200,
                "max_attempts": 2,
                "pass_score": 50,
            },
            "questions": [
                {
                    "prompt": "Hai cộng ba bằng bao nhiêu?",
                    "meta": {"type": "mcq", "points": 1},
                    "choices": [
                        {"text": "5", "is_correct": True, "position": 0},
                        {"text": "4", "is_correct": False, "position": 1},
                    ],
                },
                {
                    "prompt": "Viết số đứng sau số 5",
                    "meta": {
                        "type": "short_answer",
                        "points": 1,
                        "accepted_answers": ["6"],
                    },
                    "choices": [],
                },
                {
                    "prompt": "Nối phép tính với kết quả",
                    "meta": {
                        "type": "matching",
                        "points": 1,
                        "pairs": [
                            {"left": "1 + 1", "right": "2"},
                            {"left": "2 + 1", "right": "3"},
                        ],
                        "correct_pairs": {"L1": "R1", "L2": "R2"},
                    },
                    "choices": [],
                },
            ],
        },
        format="json",
        HTTP_HOST="localhost",
    )
    assert created.status_code == 201
    exam_id = created.data["id"]
    created_questions = created.data["questions"]
    mcq = created_questions[0]
    short_answer = created_questions[1]
    matching = created_questions[2]
    correct_choice = next(choice for choice in mcq["choices"] if choice["is_correct"])
    wrong_choice = next(choice for choice in mcq["choices"] if not choice["is_correct"])

    client = APIClient()
    client.force_authenticate(student)
    detail = client.get(f"/api/student/exams/{exam_id}/", HTTP_HOST="localhost")
    assert detail.status_code == 200
    assert [item["type"] for item in detail.data["questions"]] == [
        "mcq", "short_answer", "matching"
    ]

    started = client.post(
        f"/api/student/exams/{exam_id}/start/",
        {},
        format="json",
        HTTP_HOST="localhost",
    )
    assert started.status_code == 201
    by_id = {item["id"]: item for item in started.data["questions"]}
    assert by_id[mcq["id"]]["choices"]
    assert by_id[short_answer["id"]]["choices"] == []
    assert by_id[matching["id"]]["choices"] == []
    assert by_id[matching["id"]]["leftItems"] == [
        {"id": "L1", "text": "1 + 1"},
        {"id": "L2", "text": "2 + 1"},
    ]
    assert by_id[matching["id"]]["rightItems"] == [
        {"id": "R1", "text": "2"},
        {"id": "R2", "text": "3"},
    ]
    assert "correct_pairs" not in by_id[matching["id"]]

    submitted = client.post(
        f"/api/student/exams/{exam_id}/submit/{started.data['id']}/",
        {
            "answers": {
                mcq["id"]: {"selected_choice_id": correct_choice["id"]},
                short_answer["id"]: {"text": "6"},
                matching["id"]: {
                    "pairs": [
                        {"left_id": "L1", "right_id": "R1"},
                        {"left_id": "L2", "right_id": "R2"},
                    ]
                },
            }
        },
        format="json",
        HTTP_HOST="localhost",
    )
    assert submitted.status_code == 200
    assert submitted.data["score"] == 100.0
    assert submitted.data["correctCount"] == 3

    second_started = client.post(
        f"/api/student/exams/{exam_id}/start/",
        {},
        format="json",
        HTTP_HOST="localhost",
    )
    assert second_started.status_code == 201
    second_submitted = client.post(
        f"/api/student/exams/{exam_id}/submit/{second_started.data['id']}/",
        {
            "answers": {
                mcq["id"]: {"selected_choice_id": wrong_choice["id"]},
                short_answer["id"]: {"text": "7"},
                matching["id"]: {
                    "pairs": [
                        {"left_id": "L1", "right_id": "R2"},
                        {"left_id": "L2", "right_id": "R1"},
                    ]
                },
            }
        },
        format="json",
        HTTP_HOST="localhost",
    )
    assert second_submitted.status_code == 200
    assert second_submitted.data["score"] == 0.0

    ranking = client.get(
        f"/api/student/exams/{exam_id}/ranking/",
        HTTP_HOST="localhost",
    )
    assert ranking.status_code == 200
    assert ranking.data["participants"] == 1
    assert ranking.data["top"][0]["rank"] == 1
    assert ranking.data["top"][0]["isMe"] is True
    assert ranking.data["top"][0]["score"] == 100.0
    assert ranking.data["top"][0]["correct"] == 3
    assert ranking.data["me"]["rank"] == 1

    limit = client.post(
        f"/api/student/exams/{exam_id}/start/",
        {},
        format="json",
        HTTP_HOST="localhost",
    )
    assert limit.status_code == 400
    assert limit.data["code"] == "attempt_limit_reached"
    assert "hết số lượt làm bài" in limit.data["detail"]
    assert "Attempt ID" not in limit.data["detail"]
