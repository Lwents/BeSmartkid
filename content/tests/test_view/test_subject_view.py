# content/tests/test_subjects.py
import pytest
from django.urls import reverse

from content.models import Subject

BASE = "/api/"

@pytest.mark.django_db
def test_create_subject(auth_client):
    client, user, token = auth_client
    payload = {"title": "Toán", "slug": "toan"}
    resp = client.post(f"{BASE}subjects/", payload, format="json")
    assert resp.status_code == 201
    assert resp.data["title"] == "Toán"
    assert Subject.objects.filter(slug="toan").exists()

@pytest.mark.django_db
def test_list_and_retrieve_subject(api_client, subject_factory=None):
    # create many subjects
    from content.tests.factories import SubjectFactory
    s1 = SubjectFactory()
    s2 = SubjectFactory()
    client = api_client
    resp = client.get(f"{BASE}subjects/")
    assert resp.status_code == 200
    # expect at least 2 in list
    assert any(s["id"] == str(s1.id) for s in resp.data)

    # retrieve
    resp2 = client.get(f"{BASE}subjects/{s1.id}/")
    assert resp2.status_code == 200
    assert resp2.data["title"] == s1.title

@pytest.mark.django_db
def test_update_subject_by_admin(admin_auth_client):
    client, admin, token = admin_auth_client
    from content.tests.factories import SubjectFactory
    subj = SubjectFactory(title="Old", slug="old")
    payload = {"title": "New"}
    resp = client.patch(f"{BASE}subjects/{subj.id}/", payload, format="json")
    assert resp.status_code == 200
    assert resp.data["title"] == "New"
