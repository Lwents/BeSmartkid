# content/tests/conftest.py
import pytest
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from content.tests.factories import UserFactory 

@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture
def user_factory(db):
    def _create_user(**kwargs):
        return UserFactory(**kwargs)
    return _create_user

@pytest.fixture
def auth_client(db, api_client, user_factory):
    """
    Returns (client, user, token) for a newly created user with default password 'password123'
    Usage:
        client, user, token = auth_client
    """
    user = user_factory()
    token, _ = Token.objects.get_or_create(user=user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return api_client, user, token

@pytest.fixture
def admin_auth_client(db, api_client, user_factory):
    admin = user_factory(role="admin", is_staff=True, username="admin1", email="admin1@example.com")
    token, _ = Token.objects.get_or_create(user=admin)
    api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return api_client, admin, token
