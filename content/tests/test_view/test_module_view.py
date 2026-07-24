# content/tests/test_modules.py
import pytest
from content.tests.factories import CourseFactory, ModuleFactory
from content.models import Module
BASE = "/api/"

@pytest.mark.django_db
def test_create_module_under_course(auth_client):
    client, user, token = auth_client
    course = CourseFactory(owner=user)
    payload = {"title": "Intro"}
    resp = client.post(f"{BASE}courses/{course.id}/modules/", payload, format="json")
    assert resp.status_code == 201
    assert Module.objects.filter(course=course, title="Intro").exists()

@pytest.mark.django_db
def test_reorder_modules(admin_auth_client):
    client, admin, token = admin_auth_client
    course = CourseFactory(owner=admin)
    # create 3 modules
    m1 = ModuleFactory(course=course, title="A", position=0)
    m2 = ModuleFactory(course=course, title="B", position=1)
    m3 = ModuleFactory(course=course, title="C", position=2)
    order_map = {str(m3.id): 0, str(m1.id): 1, str(m2.id): 2}
    resp = client.post(f"{BASE}courses/{course.id}/modules/reorder/", {"order_map": order_map}, format="json")
    assert resp.status_code in (200, 204)
    # reload
    m1.refresh_from_db(); m2.refresh_from_db(); m3.refresh_from_db()
    positions = {m1.title: m1.position, m2.title: m2.position, m3.title: m3.position}
    assert positions["C"] == 0
