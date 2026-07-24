import pytest
from datetime import date
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils import timezone

from custom_account.models import UserModel, Profile, ParentalConsent
from custom_account.services import user_service, auth_service
from custom_account.tests.factories import UserFactory, ProfileFactory, ParentalConsentFactory
from infrastructure import email_service as email_infra



@pytest.mark.django_db
def test_reset_password_request_calls_email(user_factory, dummy_email):
    user = user_factory(email="parent@example.com")

    # auth_service should call adapter
    auth_service.reset_password_request(user.email)
    assert len(dummy_email) == 1
    assert dummy_email[0]["to"] == user.email
    assert "reset-password" in dummy_email[0]["body"].lower() or "reset" in dummy_email[0]["body"].lower()


@pytest.mark.django_db
def test_reset_password_confirm_with_valid_and_invalid_token(user_factory):
    user = user_factory(email="kid@ex.com", password="OldPass123")
    token = PasswordResetTokenGenerator().make_token(user)

    # valid token -> True and password updated
    ok = auth_service.reset_password_confirm(email=user.email, token=token, new_password="NewP@ss99")
    assert ok is True
    user.refresh_from_db()
    assert user.check_password("NewP@ss99")

    # invalid token -> False
    user.set_password("Start1")
    user.save()
    bad = auth_service.reset_password_confirm(email=user.email, token="badtoken", new_password="Xx12Xx12")
    assert bad is False


@pytest.mark.django_db
def test_reset_password_request_nonexistent_email_raises_or_noop():
    # Implementation may raise ValueError or silently ignore; ensure one consistent behavior in your services.
    with pytest.raises(Exception):
        auth_service.reset_password_request("does-not-exist@example.com")