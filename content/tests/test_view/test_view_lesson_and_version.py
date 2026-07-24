# content/tests/test_lessons_and_versions.py
import pytest
from content.tests.factories import CourseFactory, ModuleFactory, LessonFactory
from content.models import Lesson, LessonVersion
BASE = "/api/"

@pytest.mark.django_db
def test_create_lesson_and_version_publish(auth_client):
    client, user, token = auth_client
    course = CourseFactory(owner=user)
    mod_resp = client.post(f"{BASE}courses/{course.id}/modules/", {"title": "M"}, format="json")
    module_id = mod_resp.data["id"]

    # create lesson
    resp = client.post(f"{BASE}modules/{module_id}/lessons/", {"title": "L1"}, format="json")
    assert resp.status_code == 201
    lesson_id = resp.data["id"]

    # create version
    payload_v = {"author_id": user.id, "content": {"content_blocks": [{"type": "text", "payload": {"text": "abc"}}]}}
    resp_v = client.post(f"{BASE}lessons/{lesson_id}/versions/", payload_v, format="json")
    assert resp_v.status_code == 201
    # assert db
    assert LessonVersion.objects.filter(lesson_id=lesson_id, version=1).exists()

    # publish version
    resp_pub = client.post(f"{BASE}lessons/{lesson_id}/versions/publish/", {"version": 1}, format="json")
    assert resp_pub.status_code in (200, 201, 204)
    lv = LessonVersion.objects.get(lesson_id=lesson_id, version=1)
    assert lv.status == "published" or lv.status == "review" or lv.published_at is not None

@pytest.mark.django_db
def test_publish_lesson_by_non_owner_denied(auth_client, user_factory):
    client, owner, token = auth_client
    # create course/lesson owned by another user
    other = user_factory(username="other")
    course = CourseFactory(owner=other)
    mod = ModuleFactory(course=course)
    lesson = LessonFactory(module=mod)
    # attempt to publish as owner (not owner of lesson) -> should be denied (403) if IsOwnerOrAdmin enforced
    resp = client.post(f"{BASE}lessons/{lesson.id}/publish/", {"published": True}, format="json")
    assert resp.status_code in (403, 401, 400)  # depending on permission config
