# content/tests/test_integration_exploration_flow.py
import pytest
from rest_framework.authtoken.models import Token
from content import models
from content.tests.factories import UserFactory

BASE = "/api/"

@pytest.mark.django_db
def test_exploration_authoring_publish_and_student_flow(api_client, user_factory):
    """
    - Author creates exploration, states, transitions.
    - Sets initial state and publishes exploration.
    - Student fetches exploration structure and can follow transitions client-side.
    """
    client = api_client
    author = user_factory(username="author1", role="instructor")
    token, _ = Token.objects.get_or_create(user=author)
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    # create exploration
    payload = {"title": "Numbers Quiz", "owner_id": author.id, "language": "vi", "schema_version": 1}
    resp = client.post(f"{BASE}explorations/", payload, format="json")
    assert resp.status_code == 201
    exp_id = resp.data["id"]

    # add states A and B
    resp_a = client.post(f"{BASE}explorations/{exp_id}/states/", {"name": "A", "content": {"prompt": "Q1"}, "interaction": {"type": "text"}}, format="json")
    assert resp_a.status_code == 201
    resp_b = client.post(f"{BASE}explorations/{exp_id}/states/", {"name": "B", "content": {"prompt": "Q2"}, "interaction": {"type": "text"}}, format="json")
    assert resp_b.status_code == 201

    # add transition A -> B
    resp_t = client.post(f"{BASE}explorations/{exp_id}/transitions/", {"from_state": "A", "to_state": "B", "condition": {"always": True}}, format="json")
    assert resp_t.status_code == 201

    # set initial state via PATCH
    resp_patch = client.patch(f"{BASE}explorations/{exp_id}/", {"initial_state_name": "A"}, format="json")
    assert resp_patch.status_code in (200, 204)

    # publish exploration
    resp_pub = client.post(f"{BASE}explorations/{exp_id}/publish/", {"published": True}, format="json")
    assert resp_pub.status_code in (200, 201)

    # student fetch exploration structure
    student = user_factory(username="learner1", role="student")
    s_token, _ = Token.objects.get_or_create(user=student)
    client.credentials(HTTP_AUTHORIZATION=f"Token {s_token.key}")

    resp = client.get(f"{BASE}explorations/{exp_id}/")
    assert resp.status_code == 200
    data = resp.data
    # check initial_state_name present and states list includes A and B
    assert data.get("initial_state_name") == "A"
    state_names = [s["name"] for s in data.get("states", [])]
    assert "A" in state_names and "B" in state_names

    # client-side simulate: starting at A, find transitions from A and go to B
    transitions = data.get("transitions", [])
    next_states = [t for t in transitions if t["from_state"] == "A"]
    assert any(t["to_state"] == "B" for t in next_states)

@pytest.mark.django_db
def test_exploration_publish_rejects_unreachable_state(api_client, user_factory):
    client = api_client
    author = user_factory(username="author2", role="instructor")
    token, _ = Token.objects.get_or_create(user=author)
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    # create exploration
    resp = client.post(f"{BASE}explorations/", {"title": "BrokenExp", "owner_id": author.id}, format="json")
    assert resp.status_code == 201
    exp_id = resp.data["id"]

    # add two states but no transition (B unreachable)
    client.post(f"{BASE}explorations/{exp_id}/states/", {"name": "A", "content": {"prompt": "A"}, "interaction": {"type": "text"}}, format="json")
    client.post(f"{BASE}explorations/{exp_id}/states/", {"name": "B", "content": {"prompt": "B"}, "interaction": {"type": "text"}}, format="json")
    client.patch(f"{BASE}explorations/{exp_id}/", {"initial_state_name": "A"}, format="json")

    # try publish -> domain should reject due to unreachable state B
    resp_pub = client.post(f"{BASE}explorations/{exp_id}/publish/", {"published": True}, format="json")
    assert resp_pub.status_code in (400, 422)
