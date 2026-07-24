# account/tests/test_domain_user.py
import pytest
from datetime import datetime
from custom_account.domains.user_domain import UserDomain

def test_userdomain_validates_required_fields():
    u = UserDomain(username="alice", email="alice@example.com")
    u.validate()  # should not raise

def test_userdomain_missing_username_raises():
    u = UserDomain(username="", email="a@b.com")
    with pytest.raises(ValueError, match="Username is required"):
        u.validate()

def test_userdomain_missing_email_raises():
    u = UserDomain(username="bob", email="")
    with pytest.raises(ValueError, match="Email is required"):
        u.validate()

def test_userdomain_invalid_email_format():
    u = UserDomain(username="bob", email="invalid-email")
    with pytest.raises(ValueError, match="Invalid email format"):
        u.validate()

def test_userdomain_invalid_role():
    u = UserDomain(username="carl", email="carl@ex.com", role="superhero")
    with pytest.raises(ValueError, match="Role must be one of"):
        u.validate()

def test_userdomain_to_dict_and_back():
    u = UserDomain(username="dana", email="dana@ex.com", role="student")
    d = u.to_dict()
    u2 = UserDomain.from_dict(d)
    assert u2.username == "dana"

