# account/tests/test_domain_profile.py
import pytest
from datetime import date
from custom_account.domains.profile_domain import ProfileDomain

def test_profiledomain_valid_data():
    p = ProfileDomain(user_id=1, display_name="Alice", dob=date(2010, 1, 1), gender="female")
    p.validate()  # should pass
    assert p.to_dict()["display_name"] == "Alice"

def test_profiledomain_missing_user_id():
    p = ProfileDomain(user_id=None, display_name="Anon")
    with pytest.raises(ValueError, match="user_id is required"):
        p.validate()

def test_profiledomain_dob_future_invalid():
    future_dob = date.today().replace(year=date.today().year + 1)
    p = ProfileDomain(user_id=1, display_name="Kid", dob=future_dob)
    with pytest.raises(ValueError, match="Date of birth cannot be in the future"):
        p.validate()

def test_profiledomain_to_from_dict_roundtrip():
    d = {"user_id": 1, "display_name": "Kid", "dob": date(2015, 5, 5), "gender": "other"}
    p = ProfileDomain.from_dict(d)
    d2 = p.to_dict()
    assert d2["display_name"] == "Kid"
