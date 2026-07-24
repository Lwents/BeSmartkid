import json
from rest_framework import status
from django.urls import reverse

from custom_account.serializers import UserSerializer
from custom_account.services import user_service
from custom_account.tests.base_test import BaseAPITestCase

class TokenTests(BaseAPITestCase):
    def setUp(self):
        # Register and login student
        student_register = self.register_user(username="student", password="Secure123", email="student@gmail.com")
        self.assertEqual(student_register.status_code, status.HTTP_201_CREATED)
        student_login = self.login_user(username_or_email="student", password="Secure123")
        self.assertEqual(student_login.status_code, status.HTTP_200_OK)
        self.student_access = student_login.data.get("access")
        self.student_refresh = student_login.data.get("refresh")
        self.student_id = student_login.data.get("user", {}).get("id")

        # Register and login admin
        admin_register = self.register_user(username="admin", password="Secure123", email="admin@gmail.com")
        self.assertEqual(admin_register.status_code, status.HTTP_201_CREATED)

        # Update admin role through service layer
        admin_domain = user_service.get_user_by_username("admin")
        admin_domain.role = "admin"
        admin_domain.is_staff = True
        admin_update = UserSerializer(admin_domain).data
        admin_update["is_staff"] = admin_domain.is_staff
        
        user_service.update_user(user_id=admin_domain.id, updates=admin_update)
        admin_login = self.login_user(username_or_email="admin", password="Secure123")
        self.assertEqual(admin_login.status_code, status.HTTP_200_OK)
        self.admin_access = admin_login.data.get("access")
    

    def test_refresh_token_success(self):
        url = reverse("token_refresh")
        res = self.client.post(url, {"refresh": self.student_refresh}, format="json")

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("access", res.data)

    def test_refresh_token_invalid(self):
        url = reverse("token_refresh")
        res = self.client.post(url, {"refresh": "not_a_real_token"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("detail", res.data)

    def test_access_token_allows_protected_endpoint(self):
        # protected API
        protected_url = reverse("account-profile")

        # With valid token
        res = self.client.get(protected_url, HTTP_AUTHORIZATION=f"Bearer {self.student_access}")
        self.assertNotEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

        # With invalid token
        res_invalid = self.client.get(protected_url, HTTP_AUTHORIZATION="Bearer fake.token")
        self.assertEqual(res_invalid.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_student_permissions_with_helper(self):
        # Student cannot view admin's profile
        self.assert_user_can_access_profile(self.student_access, "admin", should_success=False)

        # Admin can view student's profile
        self.assert_user_can_access_profile(self.admin_access, "student", should_success=True)

        # Admin can view their own profile
        self.assert_user_can_access_profile(self.admin_access, "admin", should_success=True)

