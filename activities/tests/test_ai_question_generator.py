import json
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from activities.api.views.exercise_view import GenerateQuestionsAIView
from activities.services.ai_question_generator import (
    normalize_ai_questions,
    parse_ai_questions,
)
from custom_account.models import UserModel


def _question(number):
    return {
        "type": "single",
        "text": f"Câu hỏi kiểm tra số {number}?",
        "score": 1,
        "choices": ["Đáp án đúng", "Đáp án sai 1", "Đáp án sai 2"],
        "correct_indices": [0],
    }


def test_parser_recovers_complete_questions_from_truncated_json():
    raw = (
        '```json\n{"questions": ['
        + json.dumps(_question(1), ensure_ascii=False)
        + ","
        + json.dumps(_question(2), ensure_ascii=False)
        + ',{"type":"single","text":"Câu bị cắt"'
    )

    normalized = normalize_ai_questions(parse_ai_questions(raw))

    assert [item["text"] for item in normalized] == [
        "Câu hỏi kiểm tra số 1?",
        "Câu hỏi kiểm tra số 2?",
    ]


def test_normalizer_supports_aliases_and_rejects_broken_questions():
    candidates = [
        {
            "question": "Hai cộng ba bằng bao nhiêu?",
            "options": [
                {"label": "5", "correct": True},
                {"label": "4"},
                {"label": "6"},
            ],
        },
        {"prompt": "Trái Đất hình vuông.", "type": "boolean", "answer": "sai"},
        {"text": "Câu lỗi", "choices": ["Một phương án"]},
    ]

    normalized = normalize_ai_questions(candidates)

    assert len(normalized) == 2
    assert normalized[0]["choices"] == ["5", "4", "6"]
    assert normalized[0]["correct_indices"] == [0]
    assert normalized[1]["choices"] == ["Đúng", "Sai"]
    assert normalized[1]["correct_indices"] == [1]


@pytest.mark.django_db
def test_generate_questions_endpoint_batches_and_returns_all_30_questions():
    teacher = UserModel.objects.create_user(
        username="ai-question-teacher",
        email="ai-question-teacher@example.com",
        password="password123",
        role="instructor",
    )
    client = APIClient()
    client.force_authenticate(teacher)
    call_state = {"next": 1}

    def fake_provider(_view, _prompt, model, expected_count=5):
        start = call_state["next"]
        questions = [_question(number) for number in range(start, start + expected_count)]
        call_state["next"] += expected_count
        return {
            "model": model,
            "text": json.dumps({"questions": questions}, ensure_ascii=False),
        }

    upload = SimpleUploadedFile(
        "toan-lop-1.txt",
        "Hai cộng ba bằng năm. Năm trừ hai bằng ba.".encode(),
        content_type="text/plain",
    )
    with patch.object(
        GenerateQuestionsAIView,
        "_call_openrouter_api",
        autospec=True,
        side_effect=fake_provider,
    ) as provider:
        response = client.post(
            "/api/activities/ai/generate-questions/",
            {"file": upload, "count": "30", "level": "Lớp 1"},
            format="multipart",
            HTTP_HOST="localhost",
        )

    assert response.status_code == 200
    assert response.data["requestedCount"] == 30
    assert response.data["generatedCount"] == 30
    assert response.data["complete"] is True
    assert len(response.data["questions"]) == 30
    assert provider.call_count == 4


@pytest.mark.django_db
def test_generate_questions_endpoint_refills_missing_or_invalid_questions():
    teacher = UserModel.objects.create_user(
        username="ai-refill-teacher",
        email="ai-refill-teacher@example.com",
        password="password123",
        role="instructor",
    )
    client = APIClient()
    client.force_authenticate(teacher)
    responses = [
        {"questions": [_question(1), {"text": "Câu lỗi", "choices": ["A"]}]},
        {"questions": [_question(2), _question(3)]},
    ]

    def fake_provider(_view, _prompt, model, expected_count=5):
        return {
            "model": model,
            "text": json.dumps(responses.pop(0), ensure_ascii=False),
        }

    upload = SimpleUploadedFile("lesson.txt", b"Lesson text", content_type="text/plain")
    with patch.object(
        GenerateQuestionsAIView,
        "_call_openrouter_api",
        autospec=True,
        side_effect=fake_provider,
    ) as provider:
        response = client.post(
            "/api/activities/ai/generate-questions/",
            {"file": upload, "count": "3"},
            format="multipart",
            HTTP_HOST="localhost",
        )

    assert response.status_code == 200
    assert response.data["generatedCount"] == 3
    assert response.data["complete"] is True
    assert provider.call_count == 2


@pytest.mark.django_db
def test_generate_questions_endpoint_rejects_invalid_count():
    teacher = UserModel.objects.create_user(
        username="ai-count-teacher",
        email="ai-count-teacher@example.com",
        password="password123",
        role="instructor",
    )
    client = APIClient()
    client.force_authenticate(teacher)
    upload = SimpleUploadedFile("lesson.txt", b"Lesson text", content_type="text/plain")

    response = client.post(
        "/api/activities/ai/generate-questions/",
        {"file": upload, "count": "thirty"},
        format="multipart",
        HTTP_HOST="localhost",
    )

    assert response.status_code == 400
    assert "1 đến 30" in response.data["detail"]
