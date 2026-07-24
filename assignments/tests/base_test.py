# tests/base_test.py
"""Base test classes."""
import pytest
from rest_framework.test import APITestCase
from django.test import TestCase


class BaseTestCase(TestCase):
    """Base test case for unit tests."""
    
    def setUp(self):
        """Setup test case."""
        super().setUp()


class BaseAPITestCase(APITestCase):
    """Base test case for API tests."""
    
    def setUp(self):
        """Setup API test case."""
        super().setUp()
    
    def authenticate_user(self, user):
        """Authenticate user for API calls."""
        self.client.force_authenticate(user=user)