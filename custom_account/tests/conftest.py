# account/tests/conftest.py

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from custom_account.tests.factories import UserFactory, ProfileFactory
from custom_account.tests.support.auth_client import AuthClient



@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user_factory(db):
    def create_user(**kwargs):
        return UserFactory(**kwargs)
    return create_user


@pytest.fixture
def dummy_email(monkeypatch):
    sent = []
    
    class DummyService:
        def send(self, to, subject, body, from_email=None):
            sent.append({"to": to, "subject": subject, "body": body})

    dummy_service = DummyService()
    monkeypatch.setattr(
        "custom_account.services.auth_service.get_email_service",
        lambda: dummy_service,
    )
    return sent


# @pytest.fixture
# def auth_client(api_client):
#     def _auth_client(user):
#         refresh = RefreshToken.for_user(user)
#         access = str(refresh.access_token)
#         api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
#         return api_client
#     return _auth_client


@pytest.fixture
def default_auth_client(user_factory, auth_client):
    user = user_factory()
    client = auth_client(user)
    return AuthClient(client, user, None, None)

@pytest.fixture
def auth_client(api_client):
    def _auth_client(user):
        client = APIClient()
        refresh = RefreshToken.for_user(user)
        access = str(refresh.access_token)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        return client
    return _auth_client

@pytest.fixture
def auth_client_with_token(api_client):
    def _auth_client(user):
        client = APIClient()
        refresh = RefreshToken.for_user(user)
        access = str(refresh.access_token)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        return client, user, str(access), str(refresh)
    return _auth_client


@pytest.fixture
def admin_auth_client(db, django_user_model):
    admin = django_user_model.objects.create_superuser(username="admin", email="admin@gmail.com", password="pass")
    client = APIClient()

    # login để lấy JWT
    response = client.post("/api/account/login/", {"username_or_email": "admin", "password": "pass"}, format='json')
    token = response.data["access"]

    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client, admin, token


@pytest.fixture
def profile_factory(db):
    return ProfileFactory

