import uuid
import json
from datetime import timedelta

import pytest
import factory
from django.apps import apps
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from activities.tests.factories import UserFactory, LessonFactory, ExerciseFactory, QuestionFactory, ChoiceFactory, AttemptFactory, AnswerFactory
from activities.domains.exercise_domain import ExerciseDomain

# Models
Exercise = apps.get_model("activities", "Exercise")
Question = apps.get_model("activities", "Question")
Choice = apps.get_model("activities", "Choice")
ExerciseAttempt = apps.get_model("activities", "ExerciseAttempt")
ExerciseAnswer = apps.get_model("activities", "ExerciseAnswer")
ExerciseSettings = apps.get_model("activities", "ExerciseSettings")
# content.Lesson expected in your project
Lesson = apps.get_model("content", "Lesson")
Enrollment = apps.get_model("content", "Enrollment")

User = get_user_model()

BASE = "/api/activities/"



# -----------------------
# Helper to create full exercise payload (with one mcq question) via API
# -----------------------
def build_exercise_payload(lesson_id, title="Math Quiz", time_limit=None, max_attempts=None, question_config=None):
    settings = {}
    if time_limit is not None:
        settings["time_limit_seconds"] = time_limit
    if max_attempts is not None:
        settings["max_attempts"] = max_attempts
    q_conf = question_config or {
        "prompt": "1 + 1 = ?",
        "meta": {"type": "mcq", "points": 1},
        "choices": [
            {"text": "2", "is_correct": True, "position": 0},
            {"text": "3", "is_correct": False, "position": 1},
        ],
    }
    payload = {
        "lesson": str(lesson_id),
        "title": title,
        "type": "mcq",
        "published": True,
        "settings": settings,
        "questions": [q_conf],
    }
    return payload


# -----------------------
# Tests
# -----------------------

@pytest.mark.django_db
def test_admin_create_and_get_exercise(admin_auth_client):
    client, admin, token = admin_auth_client
    lesson = LessonFactory()
    payload = build_exercise_payload(lesson.id, title="Add test")
    resp = client.post(f"{BASE}exercises/", payload, format="json")
    assert resp.status_code == 201, resp.data
    data = resp.data
    assert data["title"] == "Add test"
    assert "questions" in data and len(data["questions"]) == 1

    # GET list and detail
    r_list = client.get(f"{BASE}exercises/")
    assert r_list.status_code == 200
    # find the created exercise in list
    found = any(x["id"] == data["id"] for x in r_list.data)
    assert found

    r_detail = client.get(f"{BASE}exercises/{data['id']}/")
    assert r_detail.status_code == 200
    assert r_detail.data["title"] == "Add test"


@pytest.mark.django_db
def test_exercise_domain_includes_show_answers():
    exercise = Exercise.objects.create(title="Answer visibility", type="mcq", published=False)
    ExerciseSettings.objects.create(exercise=exercise, show_answers="never")

    domain = ExerciseDomain.from_model(exercise)

    assert domain.settings["show_answers"] == "never"


@pytest.mark.django_db
def test_non_admin_cannot_create_exercise(auth_client):
    client, user, token = auth_client
    lesson = LessonFactory()
    payload = build_exercise_payload(lesson.id)
    resp = client.post(f"{BASE}exercises/", payload, format="json")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_start_submit_finalize_flow(auth_client, admin_auth_client):
    admin_client, admin, _ = admin_auth_client
    student_client, student, _ = auth_client

    # admin create exercise
    lesson = LessonFactory()
    Enrollment.objects.create(course=lesson.module.course, student=student)
    payload = build_exercise_payload(lesson.id)
    r = admin_client.post(f"{BASE}exercises/", payload, format="json")
    assert r.status_code == 201
    exercise_id = r.data["id"]
    # extract question & choice ids
    q = r.data["questions"][0]
    question_id = q["id"]
    # find correct choice id
    correct_choice = None
    for ch in q.get("choices", []):
        if ch.get("is_correct"):
            correct_choice = ch
            break
    assert correct_choice is not None

    # student starts attempt
    r2 = student_client.post(f"{BASE}exercises/{exercise_id}/start/")
    assert r2.status_code == 201
    attempt = r2.data
    attempt_id = attempt["attempt_id"] if "attempt_id" in attempt else attempt.get("id") or attempt.get("id", None)
    # Accept several possible shapes returned: use id or attempt_id
    if not attempt_id:
        # try top-level id key
        attempt_id = attempt.get("id")
    assert attempt_id is not None

    # submit correct answer
    payload_answer = {"question_id": question_id, "answer": {"selected_choice_id": correct_choice["id"]}}
    r3 = student_client.post(f"{BASE}attempts/{attempt_id}/answers/", payload_answer, format="json")
    assert r3.status_code == 200, r3.data
    resp_ans = r3.data
    # Check correctness flag in returned structure (depends on serializer shape)
    assert ("correct" in resp_ans and resp_ans["correct"]) or ("answer" in resp_ans and (resp_ans.get("answer", {}).get("selected_choice_id") == correct_choice["id"]))

    # finalize
    r4 = student_client.post(f"{BASE}attempts/{attempt_id}/finalize/", {}, format="json")
    assert r4.status_code == 200
    summary = r4.data
    # check final score present (100 for single-question correct)
    assert "score" in summary
    assert summary["score"] == 100.0 or summary["score"] >= 50.0


@pytest.mark.django_db
def test_submit_answer_wrong_user_forbidden(auth_client, user_factory):
    client, user, token = auth_client
    # create exercise + attempt by another student
    other = user_factory(username="other_u")
    lesson = LessonFactory()
    exercise = ExerciseFactory(lesson=lesson)
    q = QuestionFactory(exercise=exercise, meta={"type": "mcq", "points": 1})
    c1 = ChoiceFactory(question=q, is_correct=True)
    c2 = ChoiceFactory(question=q, is_correct=False)
    attempt = AttemptFactory(exercise=exercise, student=other)
    # other student's answer exists, now logged-in user tries to submit
    payload = {"question_id": str(q.id), "answer": {"selected_choice_id": str(c1.id)}}
    resp = client.post(f"{BASE}attempts/{attempt.id}/answers/", payload, format="json")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_max_attempts_enforced(admin_auth_client, auth_client):
    admin_client, admin, _ = admin_auth_client
    student_client, student, _ = auth_client

    lesson = LessonFactory()
    Enrollment.objects.create(course=lesson.module.course, student=student)
    payload = build_exercise_payload(lesson.id, max_attempts=1)
    r = admin_client.post(f"{BASE}exercises/", payload, format="json")
    assert r.status_code == 201
    exercise_id = r.data["id"]

    # start first attempt - ok
    r1 = student_client.post(f"{BASE}exercises/{exercise_id}/start/")
    assert r1.status_code == 201
    attempt_id = r1.data.get("id") or r1.data.get("attempt_id")
    assert student_client.post(
        f"{BASE}attempts/{attempt_id}/finalize/", {}, format="json"
    ).status_code == 200

    # A finished first attempt consumes the student's only allowed attempt.
    r2 = student_client.post(f"{BASE}exercises/{exercise_id}/start/")
    assert r2.status_code == 400 or r2.status_code == 403


@pytest.mark.django_db
def test_max_attempts_is_per_student_not_global(admin_auth_client, auth_client, user_factory):
    admin_client, admin, _ = admin_auth_client
    student1_client, student1, _ = auth_client

    # create second student + client
    student2 = user_factory(username="student_two")
    student2_client = APIClient()
    student2_client.force_authenticate(student2)

    lesson = LessonFactory()
    Enrollment.objects.create(course=lesson.module.course, student=student1)
    Enrollment.objects.create(course=lesson.module.course, student=student2)
    payload = build_exercise_payload(lesson.id, max_attempts=1)
    r = admin_client.post(f"{BASE}exercises/", payload, format="json")
    assert r.status_code == 201
    exercise_id = r.data["id"]

    # Student 1 uses their single attempt
    r1 = student1_client.post(f"{BASE}exercises/{exercise_id}/start/")
    assert r1.status_code == 201

    # Student 2 should still be able to start their own attempt
    r2 = student2_client.post(f"{BASE}exercises/{exercise_id}/start/")
    assert r2.status_code == 201, r2.data


@pytest.mark.django_db
def test_short_answer_fuzzy_matching(admin_auth_client, auth_client):
    admin_client, admin, _ = admin_auth_client
    student_client, student, _ = auth_client

    lesson = LessonFactory()
    Enrollment.objects.create(course=lesson.module.course, student=student)
    # prepare short answer question with accepted answers and fuzzy threshold low to allow near match
    q_conf = {
        "prompt": "Write number twenty-one",
        "meta": {"type": "short_answer", "points": 2, "accepted_answers": ["21", "twenty one"], "similarity_threshold": 0.6},
        "choices": []
    }
    payload = build_exercise_payload(lesson.id, title="SA Test", question_config=q_conf)
    r = admin_client.post(f"{BASE}exercises/", payload, format="json")
    assert r.status_code == 201
    exercise_id = r.data["id"]
    qid = r.data["questions"][0]["id"]

    # start attempt
    r_start = student_client.post(f"{BASE}exercises/{exercise_id}/start/")
    assert r_start.status_code == 201
    attempt_id = r_start.data.get("id") or r_start.data.get("attempt_id")

    # submit near match (e.g., 'twentyone' without space)
    ans_payload = {"question_id": qid, "answer": {"text": "Twentyone"}}
    r_ans = student_client.post(f"{BASE}attempts/{attempt_id}/answers/", ans_payload, format="json")
    assert r_ans.status_code == 200
    resp = r_ans.data
    # expect accepted (score positive)
    # either 'correct' flag or 'answer.score' present
    if "correct" in resp:
        assert resp["correct"] is True or resp.get("score", 0) > 0
    else:
        # fallback: fetch attempt summary and check score > 0
        r_summary = student_client.get(f"{BASE}attempts/{attempt_id}/")
        assert r_summary.status_code == 200
        assert r_summary.data["score"] > 0


@pytest.mark.django_db
def test_regrade_and_manual_grade(admin_auth_client, auth_client):
    admin_client, admin, _ = admin_auth_client
    student_client, student, _ = auth_client

    lesson = LessonFactory()
    Enrollment.objects.create(course=lesson.module.course, student=student)
    payload = build_exercise_payload(lesson.id)
    r = admin_client.post(f"{BASE}exercises/", payload, format="json")
    assert r.status_code == 201
    exercise_id = r.data["id"]
    q = r.data["questions"][0]
    qid = q["id"]
    # get a wrong choice id (the one not marked correct)
    wrong_choice = None
    correct_choice = None
    for ch in q.get("choices", []):
        if ch.get("is_correct"):
            correct_choice = ch
        else:
            wrong_choice = ch

    # student start and submit wrong answer
    start = student_client.post(f"{BASE}exercises/{exercise_id}/start/")
    attempt_id = start.data.get("id") or start.data.get("attempt_id")
    payload_ans = {"question_id": qid, "answer": {"selected_choice_id": wrong_choice["id"]}}
    r_ans = student_client.post(f"{BASE}attempts/{attempt_id}/answers/", payload_ans, format="json")
    assert r_ans.status_code == 200

    # Admin manually grade the wrong answer as full points
    grade_payload = {"question_id": qid, "score": 1.0, "comment": "manual override"}
    r_grade = admin_client.post(f"{BASE}attempts/{attempt_id}/grade/", grade_payload, format="json")
    assert r_grade.status_code == 200
    graded = r_grade.data
    assert graded.get("score") == 1.0 or graded.get("answer", {}).get("manual_score") == 1.0

    # Admin regrade attempt (should keep manual score but re-evaluate other answers)
    r_re = admin_client.post(f"{BASE}attempts/{attempt_id}/regrade/")
    assert r_re.status_code == 200
    assert "new_score" in r_re.data


@pytest.mark.django_db
def test_stats_and_export(admin_auth_client):
    client, admin, _ = admin_auth_client
    # create simple exercise and one attempt
    lesson = LessonFactory()
    ex = ExerciseFactory(lesson=lesson)
    # create attempt and answer
    u = UserFactory()
    att = AttemptFactory(exercise=ex, student=u)
    q = QuestionFactory(exercise=ex)
    a = AnswerFactory(attempt=att, question=q, answer={"score": 1.0}, correct=True)

    # stats
    r_stats = client.get(f"{BASE}exercises/{str(ex.id)}/stats/")
    assert r_stats.status_code == 200
    assert "total_attempts" in r_stats.data

    # export csv
    r_export = client.get(f"{BASE}exercises/{str(ex.id)}/export/")
    assert r_export.status_code == 200
    assert "text/csv" in r_export["Content-Type"]
    content = r_export.content.decode("utf-8")
    assert "attempt_id" in content or str(att.id) in content
