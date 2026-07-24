# account/tests/test_domain_consent.py
import pytest
from datetime import datetime

from custom_account.domains.parental_consent_domain import ParentalConsentDomain



def test_consentdomain_valid_data():
    c = ParentalConsentDomain(parent_id=1, child_id=2, scopes=["data_sharing"])
    c.validate()  # should pass
    assert c.to_dict()["scopes"] == ["data_sharing"]

def test_consentdomain_missing_parent_or_child():
    c1 = ParentalConsentDomain(parent_id=None, child_id=2, scopes=["x"])
    with pytest.raises(ValueError, match="Both parent and child are required"):
        c1.validate()

    c2 = ParentalConsentDomain(parent_id=1, child_id=None, scopes=["x"])
    with pytest.raises(ValueError, match="Both parent and child are required"):
        c2.validate()


def test_consentdomain_empty_scopes_invalid():
    c = ParentalConsentDomain(parent_id=1, child_id=2, scopes=[])
    with pytest.raises(ValueError, match="At least one scope must be provided"):
        c.validate()

def test_consentdomain_revoke_marks_revoked():
    c = ParentalConsentDomain(parent_id=1, child_id=2, scopes=["x"])
    assert not c.is_revoked
    c.revoke()
    assert c.is_revoked
    assert isinstance(c.revoked_at, datetime)

def test_consentdomain_to_from_dict_roundtrip():
    c = ParentalConsentDomain(parent_id=1, child_id=2, scopes=["y"])
    d = c.to_dict()
    c2 = ParentalConsentDomain.from_dict(d)
    assert c2.child_id == 2
    assert c2.scopes == ["y"]
