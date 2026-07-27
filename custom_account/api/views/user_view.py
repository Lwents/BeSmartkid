import logging
from django.http import Http404
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

from admin_api.services import record_admin_action
from custom_account.models import UserModel
from custom_account.domains.user_domain import UserDomain
from custom_account.api.dtos.user_dto import UpdateUserInput, UserPublicOutput, UserAdminOutput, UserInput
from custom_account.api.mixins import RoleBasedOutputMixin
from custom_account.serializers import (
    UserSerializer,
    ChangePasswordSerializer,
    SetPasswordSerializer,
    RegisterSerializer,
    PasswordChangeOTPVerifySerializer,
)
from custom_account.services import user_service, exceptions, password_otp_service
from custom_account.services.exceptions import DomainError



# ---------- User detail & update ----------
class CurrentUserDetailView(RoleBasedOutputMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    output_dto_public = UserPublicOutput
    output_dto_admin  = UserAdminOutput

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_service = user_service

    def get(self, request):
        return Response({"instance": request.user})

    def patch(self, request):
        if 'role' in request.data or 'is_active' in request.data:
            return Response(
                {'detail': 'Không thể tự thay đổi vai trò hoặc trạng thái tài khoản.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = UserSerializer(
            request.user,
            data=request.data,
            partial=True,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data

        # Create the DTO from ALL validated data
        update_dto = UpdateUserInput(**validated_data)

        # Create the update payload, but exclude any 'None' values.
        updates_payload = update_dto.model_dump(exclude_none=True)

        # If the payload is empty after stripping Nones, just return.
        if not updates_payload:
            return Response({"instance": request.user}, status=200)

        try:
            updated = self.user_service.update_user(
                user_id=request.user.id,
                updates=updates_payload,
            )
            return Response({"instance": updated}, status=200)
        except ValidationError as e:
            return Response({"detail": str(e)}, status=400)
        


class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            success = user_service.change_password(user_id=request.user.id, 
                                                   old_password=data["old_password"], 
                                                   new_password=data["new_password"])
        except exceptions.UserNotFoundError as e:
            return Response({"detail": str(e)}, status=status.HTTP_404_NOT_FOUND)
        except exceptions.IncorrectPasswordError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"success": True}, status=status.HTTP_200_OK)


class PasswordChangeOTPRequestView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        current_password = request.data.get("current_password")
        if not current_password:
            return Response({"detail": "Vui lòng nhập mật khẩu hiện tại."}, status=status.HTTP_400_BAD_REQUEST)
        if not request.user.check_password(current_password):
            return Response({"detail": "Mật khẩu hiện tại không chính xác."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            password_otp_service.request_password_change_otp(request.user)
        except password_otp_service.OTPThrottleError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_429_TOO_MANY_REQUESTS)

        masked_email = request.user.email
        if masked_email and "@" in masked_email:
            local, domain = masked_email.split("@", 1)
            if len(local) > 2:
                masked_email = local[0] + "***" + local[-1] + "@" + domain
            else:
                masked_email = local[0] + "***@" + domain

        return Response(
            {"detail": "OTP đã được gửi tới email", "email": masked_email},
            status=status.HTTP_200_OK,
        )


class PasswordChangeOTPConfirmView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = PasswordChangeOTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        code = serializer.validated_data["otp"]
        new_password = serializer.validated_data["new_password"]

        try:
            password_otp_service.verify_password_change_otp(request.user, code)
        except password_otp_service.OTPExpiredError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except password_otp_service.OTPInvalidError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except password_otp_service.OTPNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except password_otp_service.OTPAttemptsExceededError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        request.user.set_password(new_password)
        request.user.save(update_fields=["password"])

        return Response({"success": True}, status=status.HTTP_200_OK)
    


# ---------- List users (admin) ----------
class AdminUserListView(RoleBasedOutputMixin, APIView): 
    """
    GET /api/account/admin/users/    (admin) - List all users
    POST /api/account/admin/users/   (admin) - Create a new user
    """
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    output_dto_public = UserPublicOutput
    output_dto_admin  = UserAdminOutput

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_service = user_service 

    def get(self, request):
        import html
        import re
        
        try:
            # Get query parameters
            role = request.query_params.get('role')
            page = int(request.query_params.get('page', 1))
            page_size = int(request.query_params.get('pageSize', request.query_params.get('page_size', 50)))
            q = request.query_params.get('q')
            status_filter = request.query_params.get('status')
            from_date = request.query_params.get('from')
            to_date = request.query_params.get('to')
            sort_by = request.query_params.get('sortBy', 'createdAt')
            sort_dir = request.query_params.get('sortDir', 'descending')
            
            # Sanitize search query to prevent XSS (searchUS_21)
            if q:
                q = html.escape(q)
                # Remove potential SQL injection patterns (searchUS_20) - Django ORM handles this but extra safety
                q = re.sub(r'(--|;|\/\*|\*\/)', '', q)
            
            # Log search action (searchUS_23)
            logger.info(f"Admin user search: user={request.user.id}, query={q}, role={role}, status={status_filter}")
            
            # Service returns paginated result with DOMAIN ENTITIES
            result = self.user_service.list_all_users_for_admin(
                role=role, 
                page=page, 
                page_size=page_size,
                q=q,
                status=status_filter,
                from_date=from_date,
                to_date=to_date,
                sort_by=sort_by,
                sort_dir=sort_dir,
                exclude_user_id=request.user.id,
            )
            
            # Convert domain entities to dict for response
            users_data = []
            for user_domain in result['results']:
                role = 'admin' if getattr(user_domain, 'is_staff', False) else user_domain.role
                users_data.append({
                    'id': user_domain.id,
                    'username': user_domain.username,
                    'email': user_domain.email,
                    'role': role,
                    'is_staff': user_domain.is_staff,
                    'is_active': user_domain.is_active,
                    'phone': getattr(user_domain, 'phone', None),
                    'created_on': getattr(user_domain, 'created_on', None),
                    'updated_on': getattr(user_domain, 'updated_on', None),
                    'last_login': getattr(user_domain, 'last_login', None),
                })
            
            return Response({
                'results': users_data,
                'count': result['count'],
                'page': result['page'],
                'page_size': result['page_size'],
                'total_pages': result['total_pages']
            }, status=status.HTTP_200_OK)
        
        except Exception as e:
            return Response(
                {"detail": f"An error occurred: {str(e)}"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def post(self, request, *args, **kwargs):
        """
        Handles POST requests to create a new user.
        """
        
        # Validate raw input format (using a DRF Serializer)
        serializer = RegisterSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
            validated_data = serializer.validated_data
        except Exception:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Create Input DTO from validated data
        try:
            # This DTO handles more specific validation (e.g., Pydantic)
            user_create_dto = UserInput(**validated_data)
        except Exception as e: # Catches Pydantic validation errors
            return Response({"detail": f"Invalid input data: {e}"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            new_user_domain: UserDomain = self.user_service.register_user(data=user_create_dto.to_dict())

            # Tài khoản role=admin do quản trị viên tạo phải có is_staff để vượt
            # qua IsAdminUser của chính các API quản trị. Luồng đăng ký công khai
            # không đi qua view này nên không thể tự nâng quyền bằng trường role.
            if new_user_domain.role == 'admin':
                created_user = UserModel.objects.get(pk=new_user_domain.id)
                if not created_user.is_staff:
                    created_user.is_staff = True
                    created_user.save(update_fields=['is_staff'])
                new_user_domain = UserDomain.from_model(created_user)
            record_admin_action(
                request=request,
                action='user.create',
                target_type='user',
                target_id=new_user_domain.id,
                details={'role': new_user_domain.role},
            )
            
            # Serialize DTO -> JSON 
            return Response(
                {"instance": new_user_domain}, 
                status=status.HTTP_201_CREATED
            )
        
        except DomainError as e: # Or your specific DomainError
            # Handle business logic errors (e.g., "Email already exists")
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
        except Exception as e:
            # Catch all other unexpected errors during service execution
            logger.error(f"Unexpected error in AdminUserListView (POST): {e}", exc_info=True)
            return Response({"detail": "An unexpected error occurred during user creation."}, 
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        

logger = logging.getLogger(__name__)
class AdminUserDetailView(RoleBasedOutputMixin, APIView):
    """
    GET /api/account/admin/users/{pk}/    (admin)
    PATCH /api/account/admin/users/{pk}/  (admin)
    DELETE /api/account/admin/users/{pk}/   (admin)
    """
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    output_dto_public = UserPublicOutput
    output_dto_admin  = UserAdminOutput

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_service = user_service  

    def get_object(self, pk):
        """
        Helper method to get the user *model* from the DB.
        This is an infrastructure concern, which is fine for the View.
        """
        try:
            # Fetches the user specified by the URL's primary key (pk)
            return UserModel.objects.get(pk=pk)
        except UserModel.DoesNotExist:
            raise Http404

    def get(self, request, pk, *args, **kwargs):
        """
        Handles GET requests to retrieve a single user.
        """
        instance = self.get_object(pk)

        # The 'RoleBasedOutputMixin' will intercept raw model instance and 
        # convert it to the correct DTO (UserAdminOutput).
        return Response({"instance": instance})

    def patch(self, request, pk, *args, **kwargs):
        """
        Handles PATCH requests to update a single user.
        This follows the DDD "Command" flow.
        """
        instance = self.get_object(pk)

        if instance.pk == request.user.pk and (
            'role' in request.data or 'is_active' in request.data
        ):
            return Response(
                {'detail': 'Bạn không thể tự hạ quyền hoặc khóa tài khoản của mình.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if instance.is_superuser and not request.user.is_superuser and (
            'role' in request.data or 'is_active' in request.data
        ):
            return Response(
                {'detail': 'Chỉ siêu quản trị viên mới được thay đổi tài khoản này.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Validate input using the serializer
        # Provide request in context so serializer can allow is_active/role for staff
        serializer = UserSerializer(instance, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data
        
        # Create Input DTO
        user_update_dto = UpdateUserInput(**validated_data)
        
        # Exclude 'None' values 
        updates_payload = user_update_dto.model_dump(exclude_unset=True)
        
        if not updates_payload:
            # Nothing to update, just return the current state
            return Response({"instance": instance}, status=status.HTTP_200_OK)

        try:
            updated_domain = self.user_service.update_user(
                user_id=instance.id, 
                updates=updates_payload
            )
            record_admin_action(
                request=request,
                action='user.update',
                target_type='user',
                target_id=instance.id,
                details={'fields': sorted(updates_payload.keys())},
            )
            
            # Return the Domain Entity for the mixin to process
            return Response({"instance": updated_domain}, status=status.HTTP_200_OK)
        
        except ValidationError as e: # Or DomainError
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Unexpected error in AdminUserDetailView: {e}", exc_info=True)
            return Response({"detail": "An unexpected error occurred."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
    def delete(self, request, pk, *args, **kwargs):
        """
        Handles DELETE requests to remove a single user.
        """
        # Get the object. This will raise Http404 if not found.
        instance = self.get_object(pk)
        
        try:
            # Delegate the deletion logic to the application service
            self.user_service.delete_user(user_id=instance.id)
            record_admin_action(
                request=request,
                action='user.delete',
                target_type='user',
                target_id=instance.id,
            )
            
            return Response(status=status.HTTP_204_NO_CONTENT)

        except ValidationError as e: # Or a specific DomainError
            # e.g., "Cannot delete the last admin user"
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Unexpected error in AdminUserDetailView delete: {e}", exc_info=True)
            return Response({"detail": "An unexpected error occurred."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        

class AdminChangePasswordView(APIView):
    """
    Allows admin users to change any user's password.
    """
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    def post(self, request, user_id):
        """
        Handles the POST request to change a user's password.
        The user_id is taken from the URL.
        """
        serializer = SetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            target = UserModel.objects.get(pk=user_id)
            if target.is_superuser and not request.user.is_superuser:
                return Response(
                    {'detail': 'Chỉ siêu quản trị viên mới được đặt lại mật khẩu tài khoản này.'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            # Use a new service function designed for admins
            revoked_tokens = user_service.admin_set_password(
                user_id=user_id,
                new_password=data["new_password"]
            )
            record_admin_action(
                request=request,
                action='user.password.reset',
                target_type='user',
                target_id=user_id,
                details={'revokedRefreshTokens': revoked_tokens},
            )
            
        except UserModel.DoesNotExist:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        except exceptions.UserNotFoundError as e:
            return Response({"detail": str(e)}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            # Catch other potential errors
            return Response(
                {"detail": f"An unexpected error occurred: {str(e)}"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return Response(
            {
                "detail": "Password changed successfully.",
                "revokedRefreshTokens": revoked_tokens,
            },
            status=status.HTTP_200_OK
        )


class AdminMaintenanceView(APIView):
    """
    POST /api/account/admin/users/sync-roles/  (admin)
    
    A utility endpoint to find and fix data mismatches
    between the 'is_staff' flag and the 'role' field.
    """
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.role_sync_service = user_service.synchronize_roles

    def post(self, request, *args, **kwargs):
        """
        Handles POST requests to trigger the synchronization.
        """
        try:
            report = self.role_sync_service()
            return Response(report, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error during role synchronization: {e}", exc_info=True)
            return Response(
                {"detail": f"An unexpected error occurred: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AdminBulkChangeRoleView(APIView):
    """
    POST /api/account/admin/users/bulk/role/
    Change role for multiple users at once.
    """
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    def post(self, request):
        ids = request.data.get('ids', [])
        role = request.data.get('role')
        
        if not ids:
            return Response({'detail': 'Không có user nào được chọn'}, status=status.HTTP_400_BAD_REQUEST)
        if not role:
            return Response({'detail': 'Vui lòng chọn vai trò'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Map frontend role to backend
        role_mapping = {'instructor': 'teacher', 'teacher': 'teacher', 'student': 'student', 'admin': 'admin'}
        backend_role = role_mapping.get(role, role)
        
        try:
            if backend_role == 'admin':
                UserModel.objects.filter(id__in=ids).update(role='admin', is_staff=True)
            else:
                UserModel.objects.filter(id__in=ids).update(role=backend_role, is_staff=False)
            
            return Response({'detail': f'Đã cập nhật vai trò cho {len(ids)} người dùng'}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminBulkLockView(APIView):
    """
    POST /api/account/admin/users/bulk/lock/
    Lock multiple users at once.
    """
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    def post(self, request):
        ids = request.data.get('ids', [])
        
        if not ids:
            return Response({'detail': 'Không có user nào được chọn'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            updated = UserModel.objects.filter(id__in=ids).update(is_active=False)
            return Response({'detail': f'Đã khóa {updated} tài khoản'}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminBulkUnlockView(APIView):
    """
    POST /api/account/admin/users/bulk/unlock/
    Unlock multiple users at once.
    """
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    def post(self, request):
        ids = request.data.get('ids', [])
        
        if not ids:
            return Response({'detail': 'Không có user nào được chọn'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            updated = UserModel.objects.filter(id__in=ids).update(is_active=True)
            return Response({'detail': f'Đã mở khóa {updated} tài khoản'}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminBulkBanView(APIView):
    """
    POST /api/account/admin/users/bulk/ban/
    Ban multiple users permanently.
    """
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    def post(self, request):
        ids = request.data.get('ids', [])
        
        if not ids:
            return Response({'detail': 'Không có user nào được chọn'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Ban = set is_active=False (could add a separate 'banned' field if needed)
            updated = UserModel.objects.filter(id__in=ids).update(is_active=False)
            return Response({'detail': f'Đã cấm {updated} tài khoản'}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminUserExportView(APIView):
    """
    GET /api/account/admin/users/export/
    Export users to CSV.
    """
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    def get(self, request):
        import csv
        from django.http import HttpResponse
        
        # Get filter params
        q = request.query_params.get('q')
        role = request.query_params.get('role')
        status_filter = request.query_params.get('status')
        from_date = request.query_params.get('from')
        to_date = request.query_params.get('to')
        
        # Reuse the service function
        result = user_service.list_all_users_for_admin(
            q=q, role=role, status=status_filter,
            from_date=from_date, to_date=to_date,
            page=1, page_size=10000  # Export all matching
        )
        
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="users.csv"'
        response.write('\ufeff')  # BOM for Excel
        
        writer = csv.writer(response)
        writer.writerow(['ID', 'Username', 'Email', 'Role', 'Status', 'Created At', 'Last Login'])
        
        for user in result['results']:
            role_display = 'Admin' if user.is_staff else ('Giáo viên' if user.role == 'teacher' else 'Học sinh')
            status_display = 'Hoạt động' if user.is_active else 'Đã khóa'
            writer.writerow([
                user.id,
                user.username,
                user.email,
                role_display,
                status_display,
                getattr(user, 'created_on', ''),
                getattr(user, 'last_login', ''),
            ])
        
        return response
    
