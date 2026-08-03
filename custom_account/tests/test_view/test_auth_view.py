# account/tests/test_views_auth.py
import re

import pytest
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
from django.contrib.auth.tokens import PasswordResetTokenGenerator


from infrastructure import email_service 
from custom_account.models import AuthAttempt, SecurityPolicy, UserModel



BASE = "/api/account/"

@pytest.mark.django_db
def test_register_success(api_client):
    payload = {
        "username": "alice",
        "email": "alice@example.com",
        "password": "Abcd1234",
        "role": "student",
        "phone": "0912345678",
    }
    response = api_client.post(f"{BASE}register/", payload, format="json")
    assert response.status_code == 201
    assert response.data["username"] == "alice"
    assert response.data["email"] == "alice@example.com"
    assert response.data["phone"] == "0912345678"
    # user exists in DB
    assert UserModel.objects.filter(username="alice").exists()


@pytest.mark.django_db
@pytest.mark.parametrize("phone", ["0000000000", "0000260524", "1234567890", "09123456789"])
def test_register_rejects_invalid_vietnamese_phone_numbers(api_client, phone):
    payload = {
        "username": "invalid_phone_student",
        "email": "invalid-phone@example.com",
        "password": "Abcd1234",
        "role": "student",
        "phone": phone,
    }

    response = api_client.post(f"{BASE}register/", payload, format="json")

    assert response.status_code == 400
    assert "phone" in response.data.get("errors", {})
    assert not UserModel.objects.filter(username="invalid_phone_student").exists()


@pytest.mark.django_db
def test_register_normalizes_international_vietnamese_phone_number(api_client):
    payload = {
        "username": "international_phone_student",
        "email": "international-phone@example.com",
        "password": "Abcd1234",
        "role": "student",
        "phone": "+84912345678",
    }

    response = api_client.post(f"{BASE}register/", payload, format="json")

    assert response.status_code == 201
    assert response.data["phone"] == "0912345678"
    assert UserModel.objects.get(username="international_phone_student").phone == "0912345678"


@pytest.mark.django_db
def test_register_rejects_password_shorter_than_eight_characters(api_client):
    payload = {
        "username": "short_password_student",
        "email": "short-password@example.com",
        "password": "1234567",
        "role": "student",
        "phone": "0987654321",
    }

    response = api_client.post(f"{BASE}register/", payload, format="json")

    assert response.status_code == 400
    assert "password" in response.data.get("errors", {})
    assert "ít nhất 8 ký tự" in str(response.data["errors"]["password"])
    assert not UserModel.objects.filter(username="short_password_student").exists()


@pytest.mark.django_db
def test_register_rejects_username_with_whitespace(api_client):
    payload = {
        "username": "lwent kkk",
        "email": "username-space@example.com",
        "password": "Abcd1234",
        "role": "student",
        "phone": "0976543210",
    }

    response = api_client.post(f"{BASE}register/", payload, format="json")

    assert response.status_code == 400
    assert "username" in response.data.get("errors", {})
    assert "chỉ gồm chữ không dấu" in str(response.data["errors"]["username"])
    assert not UserModel.objects.filter(username="lwent kkk").exists()


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
def test_login_is_case_insensitive_and_preserves_password_whitespace(api_client, user_factory):
    user_factory(
        username="CaseLogin",
        email="case-login@example.com",
        set_password=" SpacePass1 ",
    )

    response = api_client.post(f"{BASE}login/", {
        "username_or_email": "  CASELOGIN  ",
        "password": " SpacePass1 ",
    }, format="json")

    assert response.status_code == 200
    assert response.data["user"]["username"] == "CaseLogin"


@pytest.mark.django_db
@pytest.mark.parametrize("invalid_field", ["identifier", "password", "otp"])
def test_login_rejects_non_string_input_without_server_error(
    api_client, user_factory, invalid_field,
):
    user_factory(
        username="typed-login",
        email="typed-login@example.com",
        set_password="Password123",
    )
    payload = {
        "username_or_email": "typed-login",
        "password": "Password123",
    }
    if invalid_field == "identifier":
        payload["username_or_email"] = 123
    elif invalid_field == "password":
        payload["password"] = 12345678
    else:
        payload["otp"] = 123456

    response = api_client.post(f"{BASE}login/", payload, format="json")

    assert response.status_code == 400
    assert "định dạng" in response.data["detail"]


@pytest.mark.django_db
def test_login_rate_limit_blocks_credential_stuffing_from_same_ip(api_client):
    policy = SecurityPolicy.get_current()
    policy.rate_limit_login_failures = 2
    policy.rate_limit_window_min = 10
    policy.lockout_attempts = 10
    policy.save()
    source_ip = "client-spoof, 198.51.100.24"

    first = api_client.post(f"{BASE}login/", {
        "username_or_email": "unknown-one",
        "password": "WrongPass1",
    }, format="json", HTTP_X_FORWARDED_FOR=source_ip)
    second = api_client.post(f"{BASE}login/", {
        "username_or_email": "unknown-two",
        "password": "WrongPass1",
    }, format="json", HTTP_X_FORWARDED_FOR=source_ip)
    blocked = api_client.post(f"{BASE}login/", {
        "username_or_email": "unknown-three",
        "password": "WrongPass1",
    }, format="json", HTTP_X_FORWARDED_FOR=source_ip)

    assert first.status_code == 401
    assert second.status_code == 401
    assert blocked.status_code == 429


@pytest.mark.django_db
def test_login_ignores_invalid_forwarded_ip_instead_of_returning_server_error(api_client):
    response = api_client.post(f"{BASE}login/", {
        "username_or_email": "unknown-ip-test",
        "password": "WrongPass1",
    }, format="json", HTTP_X_FORWARDED_FOR="not-an-ip")

    assert response.status_code == 401


@pytest.mark.django_db
def test_login_does_not_trust_forwarded_ip_from_public_direct_peer(api_client):
    response = api_client.post(f"{BASE}login/", {
        "username_or_email": "public-peer-test",
        "password": "WrongPass1",
    }, format="json", REMOTE_ADDR="8.8.8.8", HTTP_X_FORWARDED_FOR="1.1.1.1")

    assert response.status_code == 401
    assert AuthAttempt.objects.get(username_or_email="public-peer-test").ip_address == "8.8.8.8"


@pytest.mark.django_db
def test_login_reports_lockout_on_the_attempt_that_triggers_it(api_client, user_factory):
    user = user_factory(
        username="lockout-login",
        email="lockout-login@example.com",
        set_password="RightPass1",
    )
    policy = SecurityPolicy.get_current()
    policy.rate_limit_login_failures = 100
    policy.lockout_attempts = 2
    policy.lockout_minutes = 30
    policy.save()

    first = api_client.post(f"{BASE}login/", {
        "username_or_email": user.username,
        "password": "WrongPass1",
    }, format="json")
    locked = api_client.post(f"{BASE}login/", {
        "username_or_email": user.username,
        "password": "WrongPass2",
    }, format="json")

    assert first.status_code == 401
    assert locked.status_code == 403
    assert "tạm thời bị khóa" in locked.data["detail"]
    user.refresh_from_db()
    assert user.lockout_until is not None


@pytest.mark.django_db
def test_teacher_two_factor_login_sends_and_accepts_one_time_code(
    api_client, user_factory, monkeypatch,
):
    sent = []

    class DummyEmailService:
        def send(self, to, subject, body, html_body=None, from_email=None):
            sent.append({"to": to, "subject": subject, "body": body})

    monkeypatch.setattr(
        "custom_account.services.login_otp_service.get_email_service",
        lambda: DummyEmailService(),
    )
    teacher = user_factory(
        username="otp-teacher",
        email="otp-teacher@example.com",
        role="instructor",
        set_password="TeacherPass1",
    )
    policy = SecurityPolicy.get_current()
    policy.twofa_enforce_teacher = True
    policy.rate_limit_login_failures = 100
    policy.save()

    requested = api_client.post(f"{BASE}login/", {
        "username_or_email": teacher.username,
        "password": "TeacherPass1",
    }, format="json")
    assert requested.status_code == 202
    assert requested.data["requires_otp"] is True
    assert len(sent) == 1
    match = re.search(r"Mã OTP đăng nhập của bạn là: (\d{6})", sent[0]["body"])
    assert match is not None
    completed = api_client.post(f"{BASE}login/", {
        "username_or_email": teacher.username,
        "password": "TeacherPass1",
        "otp": match.group(1),
    }, format="json")
    replayed = api_client.post(f"{BASE}login/", {
        "username_or_email": teacher.username,
        "password": "TeacherPass1",
        "otp": match.group(1),
    }, format="json")

    assert completed.status_code == 200
    assert completed.data["user"]["role"] == "instructor"
    assert replayed.status_code == 400


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
    assert response.status_code == 200
    assert len(dummy_email) == 1
    assert dummy_email[0]["to"] == user.email
    assert "Nếu email đã đăng ký" in response.data["detail"]


@pytest.mark.django_db
def test_reset_password_request_does_not_reveal_unknown_email(api_client, dummy_email):
    response = api_client.post(
        f"{BASE}password/reset/",
        {"email": "unknown-reset@example.com"},
        format="json",
    )

    assert response.status_code == 200
    assert "Nếu email đã đăng ký" in response.data["detail"]
    assert dummy_email == []


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
    assert response.data["detail"] == "Đặt lại mật khẩu thành công."

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
    assert "không hợp lệ hoặc đã hết hạn" in response.data["detail"]
