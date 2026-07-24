from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
import logging
import secrets
import string

from admin_api.permissions import IsAdmin
from custom_account.models import UserModel

logger = logging.getLogger(__name__)


class BulkCreateUsersView(APIView):
    """
    POST /api/admin/users/bulk-create/
    Create multiple user accounts with cohort-based naming
    
    Request body:
    {
        "cohort_code": "K72",  # K=72, A=01, B=02, etc.
        "count": 10,
        "default_password": "Student@123",
        "role": "student"  # or "teacher"
    }
    """
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request):
        """Create multiple user accounts"""
        try:
            cohort_code = request.data.get('cohort_code', '').strip().upper()
            count = int(request.data.get('count', 0))
            role = request.data.get('role', 'student').strip().lower()

            # Validation
            if not cohort_code:
                return Response({
                    'detail': 'Mã khóa không được để trống'
                }, status=status.HTTP_400_BAD_REQUEST)

            if count < 1 or count > 100:
                return Response({
                    'detail': 'Số lượng phải từ 1 đến 100'
                }, status=status.HTTP_400_BAD_REQUEST)

            if role not in ['student', 'teacher']:
                return Response({
                    'detail': 'Vai trò phải là student hoặc teacher'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Convert cohort code to number prefix
            # K -> 72, A -> 01, B -> 02, ..., Z -> 26
            prefix = self._cohort_to_prefix(cohort_code)

            created_accounts = []
            errors = []

            with transaction.atomic():
                for i in range(1, count + 1):
                    # Generate username: prefix + 5-digit sequential number
                    # Example: K72 -> 7251050101, 7251050102, ...
                    # A23 -> 0123050101, 0123050102, ...
                    username = f"{prefix}5{str(i).zfill(5)}"
                    email = f"{username}@sunnyedu.local"

                    # Check if username already exists
                    if UserModel.objects.filter(username=username).exists():
                        errors.append(f"Username {username} đã tồn tại")
                        continue

                    password = self._generate_password()

                    try:
                        # Create user
                        user = UserModel.objects.create_user(
                            username=username,
                            email=email,
                            password=password,
                            role=role
                        )

                        created_accounts.append({
                            'username': username,
                            'email': email,
                            'role': role,
                            'password': password
                        })

                    except Exception as e:
                        logger.error(f"Error creating user {username}: {e}")
                        errors.append(f"Lỗi tạo {username}: {str(e)}")

            return Response({
                'created': len(created_accounts),
                'accounts': created_accounts,
                'errors': errors
            }, status=status.HTTP_201_CREATED if created_accounts else status.HTTP_400_BAD_REQUEST)

        except ValueError as e:
            return Response({
                'detail': f'Dữ liệu không hợp lệ: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Bulk create error: {e}", exc_info=True)
            return Response({
                'detail': f'Lỗi hệ thống: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _cohort_to_prefix(self, cohort_code: str) -> str:
        """
        Convert cohort code to numeric prefix
        K72 -> 72
        A23 -> 0123 (A=01, then 23)
        B05 -> 0205 (B=02, then 05)
        """
        if not cohort_code:
            return '00'

        # Extract first letter and remaining digits
        first_char = cohort_code[0]
        remaining = cohort_code[1:] if len(cohort_code) > 1 else ''

        # Convert letter to number
        if first_char == 'K':
            # K is special - use the number directly
            return remaining.zfill(2) if remaining else '00'
        elif first_char.isalpha():
            # A=01, B=02, ..., Z=26
            letter_num = ord(first_char) - ord('A') + 1
            letter_prefix = str(letter_num).zfill(2)
            return f"{letter_prefix}{remaining.zfill(2)}"
        else:
            # If starts with number, use as is
            return cohort_code.zfill(4)

    def _generate_password(self, length: int = 8) -> str:
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(length))


class BulkCreateRollbackView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request):
        usernames = request.data.get('usernames', [])

        if not isinstance(usernames, list) or not usernames:
            return Response({
                'detail': 'Danh sách usernames không hợp lệ'
            }, status=status.HTTP_400_BAD_REQUEST)

        normalized = [str(u).strip() for u in usernames if str(u).strip()]
        if not normalized:
            return Response({
                'detail': 'Danh sách usernames không hợp lệ'
            }, status=status.HTTP_400_BAD_REQUEST)

        qs = UserModel.objects.filter(username__in=normalized, role__in=['student', 'teacher'])
        deleted, _ = qs.delete()

        logger.info("Bulk rollback deleted %s accounts", deleted)

        return Response({
            'deleted': deleted
        }, status=status.HTTP_200_OK)
