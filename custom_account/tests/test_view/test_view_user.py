# account/tests/test_views_user.py
import pytest
from rest_framework.authtoken.models import Token

from custom_account.models import UserModel
from custom_account.tests.support.auth_client import AuthClient



BASE = "/api/account/"

@pytest.mark.django_db
def test_user_detail_owner_can_get(default_auth_client: AuthClient):
    response = default_auth_client.get(f"{BASE}users/{default_auth_client.user.id}/")
    assert response.status_code == 200
    assert response.data["id"] == default_auth_client.user.id


def test_user_detail_other_forbidden(auth_client, user_factory):
    a = user_factory(username="u1")
    b = user_factory(username="u2")

    client = auth_client(b)  # AuthClient wrapper
    resp = client.get(f"{BASE}users/{a.id}/")

    assert resp.status_code == 403


@pytest.mark.django_db
def test_user_detail_other_forbidden(auth_client, user_factory):
    a = user_factory(username="u1")
    b = user_factory(username="u2")

    # login as b
    client = auth_client(b)
    resp = client.get(f"{BASE}users/{a.id}/")

    assert resp.status_code == 403  # IsOwnerOrAdmin denies


@pytest.mark.django_db
def test_user_update_owner(auth_client, user_factory):
    user = user_factory(username="mike", password="P@ssword1")
    client = auth_client(user)

    resp = client.patch(
        f"{BASE}users/{user.id}/",
        {"phone": "0123456789"},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["phone"] == "0123456789"


@pytest.mark.django_db
def test_user_update_owner(auth_client, user_factory):
    print("BEFORE:", list(UserModel.objects.values("id", "username")))
    
    user = user_factory(username="mike", password="P@ssword1")
    
    print("AFTER:", list(UserModel.objects.values("id", "username")))
    
    client = auth_client(user)

    resp = client.patch(
        f"{BASE}users/{user.id}/",
        {"phone": "0123456789"},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["phone"] == "0123456789"


@pytest.mark.django_db
def test_user_list_admin(admin_auth_client, user_factory):
    client, admin, token = admin_auth_client
    user_factory(username="u_a")
    user_factory(username="u_b")

    resp = client.get(f"{BASE}users/")
    assert resp.status_code == 200

    # it's a list view; at least 2 users plus admin present
    assert isinstance(resp.data, (list, dict))
    if isinstance(resp.data, list):
        assert len(resp.data) >= 2


@pytest.mark.django_db
def test_change_password_wrong_old(auth_client, user_factory):
    user = user_factory(password="P@ssword1")
    client = auth_client(user)

    payload = {"old_password": "wrong", "new_password": "NewP@ss1"}
    resp = client.post(f"{BASE}password/change/", payload, format="json")

    assert resp.status_code == 400
