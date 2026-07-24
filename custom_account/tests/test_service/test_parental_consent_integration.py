import pytest
from datetime import date
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils import timezone

from custom_account.models import UserModel, Profile, ParentalConsent
from custom_account.services import user_service, auth_service, parental_consent_service
from infrastructure import email_service as email_infra
from custom_account.tests.factories import UserFactory, ProfileFactory, ParentalConsentFactory



@pytest.mark.django_db
def test_grant_revoke_and_check_consent(user_factory):
    parent = user_factory(role="parent", username="p1", password="ppp")
    child = user_factory(role="student", username="c1", password="ccc")
    # grant
    consent = parental_consent_service.grant_consent(parent_id=parent.id, child_id=child.id, data={'scopes':["progress_view"]})
    assert consent is not None
    # DB entry
    assert ParentalConsent.objects.filter(parent=parent, child=child, revoked_at__isnull=True).exists()
    # has_consent
    assert parental_consent_service.has_consent(parent_id=parent.id, child_id=child.id)
    # revoke
    ok = parental_consent_service.revoke_consent(parent_id=parent.id, child_id=child.id)
    assert ok is True
    assert not parental_consent_service.has_consent(parent_id=parent.id, child_id=child.id)


@pytest.mark.django_db
def test_list_consents_for_parent(user_factory):
    parent = user_factory(role="parent", username="p_l", password="pp")
    child1 = user_factory(role="student", username="c_l1", password="c1")
    child2 = user_factory(role="student", username="c_l2", password="c2")

    # create two consents
    parental_consent_service.grant_consent(parent_id=parent.id, child_id=child1.id, data={'scopes': ["a"]})
    parental_consent_service.grant_consent(parent_id=parent.id, child_id=child2.id, data={'scopes': ["b"]})

    lst = parental_consent_service.list_consents_for_parent(parent_id=parent.id)
    assert isinstance(lst, list)
    assert len(lst) >= 2
    ids = {getattr(c, "child_id", getattr(c, "child", None) ) for c in lst}
    assert child1.id in ids and child2.id in ids