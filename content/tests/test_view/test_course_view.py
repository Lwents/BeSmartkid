# content/tests/test_courses.py
import pytest
from content.models import Course, Module, Lesson, LessonVersion
from content.tests.factories import SubjectFactory
BASE = "/api/"

@pytest.mark.django_db
def test_create_course(auth_client):
    client, user, token = auth_client
    subject = SubjectFactory()
    payload = {"title": "Math 1", "subject_id": str(subject.id), "description": "desc", "grade": "1", "owner_id": user.id}
    resp = client.post(f"{BASE}courses/", payload, format="json")
    assert resp.status_code == 201
    assert resp.data["title"] == "Math 1"
    assert Course.objects.filter(title="Math 1").exists()

@pytest.mark.django_db
def test_publish_course_requires_published_lesson(auth_client):
    client, user, token = auth_client
    # create course
    payload = {"title": "Course X", "owner_id": user.id}
    resp = client.post(f"{BASE}courses/", payload, format="json")
    assert resp.status_code == 201
    course_id = resp.data["id"]

    # create a module
    m_payload = {"title": "M1"}
    resp_m = client.post(f"{BASE}courses/{course_id}/modules/", m_payload, format="json")
    assert resp_m.status_code == 201
    module_id = resp_m.data["id"]

    # create lesson
    l_payload = {"title": "L1"}
    resp_l = client.post(f"{BASE}modules/{module_id}/lessons/", l_payload, format="json")
    assert resp_l.status_code == 201
    lesson_id = resp_l.data["id"]

    # Attempt to publish course -- should fail because no published lesson versions
    resp_pub = client.post(f"{BASE}courses/{course_id}/publish/", {"require_all_lessons_published": False}, format="json")
    assert resp_pub.status_code in (400, 422)  # domain should block publish

    # create a lesson version and mark it published (via version endpoint)
    lv_payload = {"author_id": user.id, "content": {"content_blocks": [{"type": "text", "payload": {"text": "hi"}}]}}
    resp_v = client.post(f"{BASE}lessons/{lesson_id}/versions/", lv_payload, format="json")
    assert resp_v.status_code == 201
    # publish the version
    resp_publish_v = client.post(f"{BASE}lessons/{lesson_id}/versions/publish/", {"version": 1}, format="json")
    # allow either 200 or 201 depending on implementation
    assert resp_publish_v.status_code in (200, 201, 204)

    # Now try to publish course again - should succeed
    resp_pub2 = client.post(f"{BASE}courses/{course_id}/publish/", {"require_all_lessons_published": False}, format="json")
    assert resp_pub2.status_code in (200, 201)
    # verify in DB
    course = Course.objects.get(id=course_id)
    assert course.published is True

@pytest.mark.django_db
def test_course_enroll_endpoint_returns_501_if_not_implemented(auth_client):
    client, user, token = auth_client
    payload = {"title": "Course Enroll Test", "owner_id": user.id}
    resp = client.post(f"{BASE}courses/", payload, format="json")
    course_id = resp.data["id"]
    resp_enroll = client.post(f"{BASE}courses/{course_id}/enroll/")
    assert resp_enroll.status_code in (200, 501)
