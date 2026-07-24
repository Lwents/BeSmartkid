# account/tests/test_views_auth.py
import pytest
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
from django.contrib.auth.tokens import PasswordResetTokenGenerator


from infrastructure import email_service 
from custom_account.models import UserModel



BASE = "/api/account/"

@pytest.mark.django_db
def test_register_success(api_client):
    payload = {
        "username": "alice",
        "email": "alice@example.com",
        "password": "Password123!",
        "role": "student",
        "phone": "1234567890",
    }
    response = api_client.post(f"{BASE}register/", payload, format="json")
    assert response.status_code == 201
    assert response.data["username"] == "alice"
    assert response.data["email"] == "alice@example.com"
    assert response.data["phone"] == "1234567890"
    # user exists in DB
    assert UserModel.objects.filter(username="alice").exists()


@pytest.mark.django_db
def test_login_success(api_client, user_factory):
    # create user with known password
    user = user_factory(username="bob", email="bob@gmail.com", set_password="Secret123!")
    payload = {"username_or_email": "bob@gmail.com", "password": "Secret123!"}
    response = api_client.post(f"{BASE}login/", payload, format="json")
    # print(response.json())  
    assert response.status_code == 200
    assert "access" in response.data
    assert "refresh" in response.data
    assert "user" in response.data
    assert response.data["user"]["username"] == "bob"

    
@pytest.mark.django_db
def test_login_invalid_password(api_client, user_factory):
    user = user_factory(username="carol", set_password="RightPass1")
    payload = {"username_or_email": "carol", "password": "WrongPass!"}
    response = api_client.post(f"{BASE}login/", payload, format="json")
    assert response.status_code == 401


@pytest.mark.django_db
def test_logout_success(auth_client_with_token, user_factory):
    user = user_factory(username='testuser', email='test@example.com')
    client, user, access_token, refresh_token = auth_client_with_token(user)
    
    # Make the logout request with the refresh token in the body
    response = client.post(f"{BASE}logout/", {"refresh": refresh_token}, format='json')
    assert response.status_code == 204, f"Expected 204, got {response.status_code}: {response.content}"
    
    # Verify the refresh token is blacklisted
    assert OutstandingToken.objects.filter(user=user).exists(), "Token not in outstanding tokens"
    assert BlacklistedToken.objects.filter(token__user=user).exists(), "Token not blacklisted"

    refresh_url = reverse('token_refresh')  # Endpoint refresh token mặc định của SimpleJWT
    response = client.post(refresh_url, {'refresh': refresh_token}, format='json')
    assert response.status_code == 401, (
        f"Expected 401 for blacklisted refresh token, got {response.status_code}"
    )

@pytest.mark.django_db
def test_logout_missing_refresh_token(auth_client_with_token, user_factory):
    """
    Test logout thất bại khi không gửi refresh token.
    """
    user = user_factory(username='testuser2', email='test2@example.com')
    client, user, _, _ = auth_client_with_token(user)
    
    logout_url = reverse('logout')  
    response = client.post(logout_url, {}, format='json')
    assert response.status_code == 400, (
        f"Expected 400 Bad Request for missing refresh token, got {response.status_code}"
    )
    assert not BlacklistedToken.objects.filter(token__user=user).exists(), (
        "No token should be blacklisted when logout fails"
    )

@pytest.mark.django_db
def test_logout_invalid_refresh_token(auth_client_with_token, user_factory):
    """
    Test logout thất bại khi gửi refresh token không hợp lệ.
    """
    user = user_factory(username='testuser3', email='test3@example.com')
    client, user, _, _ = auth_client_with_token(user)
    
    logout_url = reverse('logout')  # Hoặc tên URL của bạn
    response = client.post(logout_url, {'refresh': 'invalid_token'}, format='json')
    assert response.status_code == 400, (
        f"Expected 400 Bad Request for invalid refresh token, got {response.status_code}"
    )
    assert not BlacklistedToken.objects.filter(token__user=user).exists(), (
        "No token should be blacklisted with invalid refresh token"
    )


@pytest.mark.django_db
def test_reset_password_request_sends_email(api_client, user_factory, dummy_email):
    user = user_factory(email="parent@example.com")
    response = api_client.post(f"{BASE}password/reset/", {"email": user.email}, format="json")
    assert response.status_code == 204
    assert len(dummy_email) == 1
    assert dummy_email[0]["to"] == user.email


@pytest.mark.django_db
def test_reset_password_confirm(api_client, user_factory):
    user = user_factory(email="kid@ex.com", password="OldPass123")
    token = PasswordResetTokenGenerator().make_token(user)

    payload = {
        "email": user.email,
        "reset_token": token,
        "new_password": "NewSecure123!"
    }
    response = api_client.post(f"{BASE}password/reset/confirm/", payload, format="json")
    assert response.status_code == 200

    # refresh and check password updated
    user.refresh_from_db()
    assert user.check_password("NewSecure123!")


@pytest.mark.django_db
def test_reset_password_confirm_invalid_token(api_client, user_factory):
    user = user_factory(email="kid2@ex.com", password="OldPass123")
    payload = {
        "email": user.email,
        "reset_token": "invalid-token",
        "new_password": "Whatever123!"
    }
    response = api_client.post(f"{BASE}password/reset/confirm/", payload, format="json")
    assert response.status_code == 400
