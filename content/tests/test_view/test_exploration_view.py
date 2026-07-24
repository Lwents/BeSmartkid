# content/tests/test_explorations.py
import pytest
from content.tests.factories import ExplorationFactory, ExplorationStateFactory, ExplorationTransitionFactory
from content.models import Exploration
BASE = "/api/"

@pytest.mark.django_db
def test_create_exploration_and_publish(auth_client):
    client, user, token = auth_client
    payload = {"title": "Exp 1", "owner_id": user.id, "language": "vi", "schema_version": 1}
    resp = client.post(f"{BASE}explorations/", payload, format="json")
    assert resp.status_code == 201
    exp_id = resp.data["id"]

    # add states
    s1 = client.post(f"{BASE}explorations/{exp_id}/states/", {"name": "A", "content": {"prompt": "A"}, "interaction": {"type": "text"}}, format="json")
    assert s1.status_code == 201
    s2 = client.post(f"{BASE}explorations/{exp_id}/states/", {"name": "B", "content": {"prompt": "B"}, "interaction": {"type": "text"}}, format="json")
    assert s2.status_code == 201

    # add transition A -> B
    t = client.post(f"{BASE}explorations/{exp_id}/transitions/", {"from_state": "A", "to_state": "B", "condition": {"always": True}}, format="json")
    assert t.status_code == 201

    # set initial_state_name via patch
    resp_patch = client.patch(f"{BASE}explorations/{exp_id}/", {"initial_state_name": "A"}, format="json")
    assert resp_patch.status_code in (200, 204)

    # publish exploration
    resp_pub = client.post(f"{BASE}explorations/{exp_id}/publish/", {"published": True}, format="json")
    assert resp_pub.status_code in (200, 201)
    exp = Exploration.objects.get(id=exp_id)
    assert exp.published is True

@pytest.mark.django_db
def test_publish_exploration_unreachable_state_fails(auth_client):
    client, user, token = auth_client
    # create exploration and two states without transitions (B unreachable)
    resp = client.post(f"{BASE}explorations/", {"title": "Exp 2", "owner_id": user.id}, format="json")
    exp_id = resp.data["id"]
    client.post(f"{BASE}explorations/{exp_id}/states/", {"name": "A", "content": {"prompt": "A"}, "interaction": {"type": "text"}}, format="json")
    client.post(f"{BASE}explorations/{exp_id}/states/", {"name": "B", "content": {"prompt": "B"}, "interaction": {"type": "text"}}, format="json")
    # set initial to A
    client.patch(f"{BASE}explorations/{exp_id}/", {"initial_state_name": "A"}, format="json")
    # try publish -> should fail due to unreachable B (domain validation)
    resp_pub = client.post(f"{BASE}explorations/{exp_id}/publish/", {"published": True}, format="json")
    assert resp_pub.status_code in (400, 422)
