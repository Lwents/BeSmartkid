# account/tests/test_views_profile_consent.py
import pytest
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.authtoken.models import Token

from custom_account.tests.factories import ProfileFactory, UserFactory
from custom_account.models import ParentalConsent



BASE = "/api/account/"

@pytest.mark.django_db
def test_profile_get_and_patch(auth_client, user_factory, profile_factory):
    # create user and profile
    user = user_factory(username="puser")
    user.set_password("abc123")
    user.save()
    profile_factory(user=user, display_name="Before")

    client = auth_client(user)

    # GET profile
    response = client.get(f"{BASE}profile/")
    assert response.status_code == 200
    assert response.data["display_name"] == "Before"

    # PATCH profile
    response2 = client.patch(f"{BASE}profile/", {"display_name": "After"}, format="json")
    assert response2.status_code == 200

    # fetch again
    response3 = client.get(f"{BASE}profile/")
    assert response3.data["display_name"] == "After"


@pytest.mark.django_db
def test_parental_consent_flow(auth_client, user_factory):
    parent = user_factory(role="parent", username="the_parent")
    parent.set_password("p123")
    parent.save()

    child = user_factory(role="student", username="the_child")
    child.set_password("c123")
    child.save()

    client = auth_client(parent)

    # grant consent
    response = client.post(f"{BASE}consents/grant/", {"child_id": child.id, "scopes": ["progress_view"]}, format="json")
    assert response.status_code == 201
    data = response.data
    assert data["parent_id"] == parent.id or data.get("parent") == parent.id

    # list consents
    response2 = client.get(f"{BASE}consents/")
    assert response2.status_code == 200
    found = any(c.get("child_id") == child.id or c.get("child") == child.id for c in response2.data)
    assert found

    # revoke consent
    response3 = client.post(f"{BASE}consents/revoke/", {"child_id": child.id}, format="json")
    assert response3.status_code == 204


