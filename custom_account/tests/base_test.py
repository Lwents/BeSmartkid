import json
from dataclasses import dataclass
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from custom_account.models import UserModel
from custom_account.services import user_service

class AuthTestMixin:
    def register_user(self, username="bob", password="Secure123", email="bob@example.com", **extra):
        data = {"username": username, "password": password, "email": email, **extra}
        url = reverse("account-register")
        return self.client.post(url, data, format="json")
    
    def login_user(self, username_or_email="bob", password="Secure123"):
        data = {"username_or_email": username_or_email, "password": password}
        url = reverse("token_obtain_pair")
        return self.client.post(url, data, format="json")
    
    def get_authenticated_client(self, access_token):
        """Return a client with authentication headers set"""
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        return client
    
    def get_user_id_from_login(self, login_response):
        """Extract user ID from login response"""
        return login_response.data.get("user", {}).get("id")

    # def get_tokens(self, username_or_email, password):
    #     login_res = self.login_user(username_or_email, password)
    #     # pretty = json.dumps(login_res.json(), indent = 2)
    #     # print(f"Login response: {login_res.status_code}\n{pretty}")
    #     # print()
    #     # print()

    #     assert login_res.status_code == 200, "Login failed in get_tokens"
    #     return login_res.data.get("refresh"), login_res.data.get("access")
    
    def create_test_user(self, username, password, email, role="student", is_staff=False):
        """Create user through API and return access token and user info"""
        register_response = self.register_user(username=username, password=password, email=email)
        self.assertEqual(register_response.status_code, status.HTTP_201_CREATED)

        # If special role needed, update through service
        if role != "student" or is_staff:
            user_domain = user_service.get_user_domain(username=username)
            user_domain.role = role
            user_domain.is_staff = is_staff
            user_service.update_user(user_domain)

        login_res = self.login_user(username_or_email=username, password=password)
        self.assertEqual(login_res.status_code, status.HTTP_200_OK)

        return {
            "access_token": login_res.data.get("access"),
            "user_id": login_res.data.get("user", {}).get("id"),
            "username": username
        }
    
    def assert_user_can_access_profile(self, access_token, target_username, should_success=True):
        """Helper to test if a user can access another user's profile"""
        target_domain = user_service.get_user_by_username(target_username)
        url = reverse("account-profile") + f"?user_id={target_domain.id}"
        response = self.client.get(url, HTTP_AUTHORIZATION=f"Bearer {access_token}")

        if should_success:
            self.assertEqual(response.status_code, status.HTTP_200_OK)
        else:
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class BaseAPITestCase(APITestCase, AuthTestMixin):
    """Base test case with common helpers."""
    pass
