# content/tests/test_content_blocks.py
import pytest
from content.tests.factories import LessonVersionFactory
from content.models import ContentBlock
BASE = "/api/"

@pytest.mark.django_db
def test_create_text_block(auth_client):
    client, user, token = auth_client
    lv = LessonVersionFactory()
    payload = {"type": "text", "position": 0, "payload": {"text": "Hello"}}
    resp = client.post(f"{BASE}lesson-versions/{lv.lesson.id}/blocks/", payload, format="json")
    # Note: endpoint URL expects lesson_version_id; the ListCreateView uses kwarg name `lesson_version_id`
    # but in some implementations it was registered differently; try both forms gracefully.
    if resp.status_code == 404:
        # try correct url with lv.id
        resp = client.post(f"{BASE}lesson-versions/{lv.id}/blocks/", payload, format="json")
    assert resp.status_code == 201
    assert ContentBlock.objects.filter(lesson_version=lv, type="text").exists()

@pytest.mark.django_db
def test_create_image_block_invalid_payload(auth_client):
    client, user, token = auth_client
    lv = LessonVersionFactory()
    payload = {"type": "image", "position": 0, "payload": {}}  # missing url/storage_id
    resp = client.post(f"{BASE}lesson-versions/{lv.id}/blocks/", payload, format="json")
    assert resp.status_code in (400, 422)
