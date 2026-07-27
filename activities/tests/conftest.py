import uuid
import json
from datetime import timedelta

import pytest
import factory
from django.apps import apps
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from activities.tests.factories import UserFactory

# Models
Exercise = apps.get_model("activities", "Exercise")
Question = apps.get_model("activities", "Question")
Choice = apps.get_model("activities", "Choice")
ExerciseAttempt = apps.get_model("activities", "ExerciseAttempt")
ExerciseAnswer = apps.get_model("activities", "ExerciseAnswer")
# content.Lesson expected in your project
Lesson = apps.get_model("content", "Lesson")

User = get_user_model()

BASE = "/api/activities/"



# -----------------------
# Fixtures
# -----------------------
@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user_factory(db):
    def _create_user(**kwargs):
        return UserFactory(**kwargs)
    return _create_user


@pytest.fixture
def auth_client(db, user_factory):
    user = user_factory(role="student")
    client = APIClient()
    client.force_authenticate(user)
    return client, user, None


@pytest.fixture
def admin_auth_client(db, user_factory):
    admin = user_factory(
        role="admin",
        is_staff=True,
        username="admin1",
        email="admin1@example.com",
    )
    admin.is_staff = True
    admin.is_superuser = getattr(admin, "is_superuser", False) or True
    admin.save()
    client = APIClient()
    client.force_authenticate(admin)
    return client, admin, None
