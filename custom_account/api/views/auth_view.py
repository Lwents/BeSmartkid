from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone
from django.db import IntegrityError
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
from rest_framework.permissions import AllowAny
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from dj_rest_auth.registration.views import SocialLoginView
from dj_rest_auth.views import PasswordResetConfirmView

from custom_account.api.dtos.user_dto import UserInput, UserPublicOutput, UserAdminOutput
from custom_account.api.mixins import RoleBasedOutputMixin
from custom_account.serializers import (
    RegisterSerializer,
    ResetPasswordSerializer,
    PasswordResetRequestSerializer,
)
from custom_account.services import (
    user_service,
    auth_service,
    profile_service,
    login_otp_service,
    login_security_service,
    session_tracking,
)
from custom_account.services.exceptions import DomainError



class RegisterView(RoleBasedOutputMixin, APIView):
    permission_classes = [permissions.AllowAny]

    output_dto_public = UserPublicOutput
    output_dto_admin = UserAdminOutput

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        public_registration_data = dict(serializer.validated_data)
        # Đăng ký công khai chỉ được tạo học viên. Giáo viên/quản trị phải do
        # một admin đã xác thực tạo qua /account/admin/users/.
        public_registration_data['role'] = 'student'
        user_input_dto = UserInput(**public_registration_data)

        try:
            # call service with domain object
            user_domain = user_service.register_user(data=user_input_dto.to_dict()) # Pass the domain object

        except DomainError as e: # <-- Catch DomainError
            # Catch the custom domain error from your service
            return Response(
                {"detail": str(e)}, # Use "detail" for consistency with other APIs
                status=status.HTTP_400_BAD_REQUEST
            )

        except IntegrityError:
            # Catch the database error when a unique constraint fails
            return Response(
                {"error": "A user with that username or email already exists."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Put the domain object in the response so the mixin can pick it up
        return Response({"instance": user_domain}, status=status.HTTP_201_CREATED)
    

# ---------- Login -----------
class CustomLoginView(APIView):
    """
    Custom login with rate limit, lockout, and optional OTP (2FA).
    """
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        identifier = (
            request.data.get("username")
            or request.data.get("email")
            or request.data.get("username_or_email")
            or request.data.get("email_or_username")
        )
        password = request.data.get("password")
        otp = request.data.get("otp")

        if not isinstance(identifier, str) or not isinstance(password, str):
            return Response(
                {"detail": "Thông tin đăng nhập không đúng định dạng."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if otp is not None and not isinstance(otp, str):
            return Response(
                {"detail": "Mã OTP không đúng định dạng."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        identifier = identifier.strip()
        otp = otp.strip() if otp is not None else None
        if not identifier or not password:
            return Response(
                {"detail": "Thiếu thông tin đăng nhập."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        normalized = login_security_service.normalize_identifier(identifier)
        user = User.objects.filter(username__iexact=normalized).first()
        if not user:
            user = User.objects.filter(email__iexact=normalized).first()

        policy = login_security_service.get_policy()
        now = timezone.now()
        ip = login_security_service.get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        if user and not user.is_active:
            login_security_service.record_attempt(
                user=user,
                identifier=normalized,
                success=False,
                ip=ip,
                user_agent=user_agent,
                error="inactive",
            )
            return Response(
                {"detail": "Tài khoản đã bị khóa. Vui lòng liên hệ hỗ trợ."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if user and user.lockout_until:
            if user.lockout_until > now:
                login_security_service.record_attempt(
                    user=user,
                    identifier=normalized,
                    success=False,
                    ip=ip,
                    user_agent=user_agent,
                    error="lockout",
                )
                return Response(
                    {"detail": "Tài khoản tạm thời bị khóa. Vui lòng thử lại sau."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            user.lockout_until = None
            user.failed_login_count = 0
            user.last_failed_login_at = None
            user.save(update_fields=['lockout_until', 'failed_login_count', 'last_failed_login_at'])

        if login_security_service.is_rate_limited(normalized, ip, policy, now=now):
            login_security_service.record_attempt(
                user=user,
                identifier=normalized,
                success=False,
                ip=ip,
                user_agent=user_agent,
                error="rate_limited",
            )
            return Response(
                {"detail": "Quá nhiều lần đăng nhập thất bại. Vui lòng thử lại sau."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        if not user or not user.check_password(password):
            login_security_service.record_attempt(
                user=user,
                identifier=normalized,
                success=False,
                ip=ip,
                user_agent=user_agent,
                error="invalid_credentials",
            )
            lockout_triggered = login_security_service.register_failure(user, policy, now=now)
            if lockout_triggered:
                detail = (
                    "Tài khoản đã bị khóa. Vui lòng liên hệ hỗ trợ."
                    if user and not user.is_active
                    else "Tài khoản tạm thời bị khóa. Vui lòng thử lại sau."
                )
                return Response(
                    {"detail": detail},
                    status=status.HTTP_403_FORBIDDEN,
                )
            return Response(
                {"detail": "Sai tài khoản hoặc mật khẩu."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if login_security_service.is_twofa_required(user, policy):
            if not otp:
                try:
                    login_otp_service.request_login_otp(user)
                except login_otp_service.OTPThrottleError:
                    return Response(
                        {"detail": "OTP vừa được gửi, vui lòng đợi.", "requires_otp": True},
                        status=status.HTTP_202_ACCEPTED,
                    )
                return Response(
                    {"detail": "Mã OTP đã được gửi đến email.", "requires_otp": True, "otp_sent": True},
                    status=status.HTTP_202_ACCEPTED,
                )
            try:
                login_otp_service.verify_login_otp(user, otp)
            except login_otp_service.OTPExpiredError as exc:
                login_security_service.record_attempt(
                    user=user,
                    identifier=normalized,
                    success=False,
                    ip=ip,
                    user_agent=user_agent,
                    error="otp_expired",
                )
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            except login_otp_service.OTPInvalidError as exc:
                login_security_service.record_attempt(
                    user=user,
                    identifier=normalized,
                    success=False,
                    ip=ip,
                    user_agent=user_agent,
                    error="otp_invalid",
                )
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            except login_otp_service.OTPNotFoundError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            except login_otp_service.OTPAttemptsExceededError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        login_security_service.reset_failures(user)
        login_security_service.record_attempt(
            user=user,
            identifier=normalized,
            success=True,
            ip=ip,
            user_agent=user_agent,
        )
        user.last_login = now
        user.save(update_fields=['last_login'])

        try:
            profile = profile_service.get_profile_by_user(user.id)
        except ObjectDoesNotExist:
            profile = profile_service.create_default_profile(user.id)

        refresh = RefreshToken.for_user(user)
        session_tracking.register_session(user=user, refresh=refresh, request=request)
        role = "admin" if user.is_staff else (user.role or "student")
        response_data = {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": role,
                "full_name": profile.display_name or user.username,
            },
        }
        return Response(response_data, status=status.HTTP_200_OK)


class GoogleLogin(SocialLoginView):
    adapter_class = GoogleOAuth2Adapter


class ResetPasswordRequestView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]

        try:
            sent = auth_service.reset_password_request(email=email)
        except ValueError:
            # Không tiết lộ email nào đã đăng ký để tránh dò tài khoản.
            sent = True
        except Exception:
            return Response(
                {"detail": "Chưa thể gửi email lúc này. Vui lòng thử lại sau."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if sent:
            return Response({
                "detail": "Nếu email đã đăng ký, hướng dẫn đặt lại mật khẩu sẽ được gửi đến bạn."
            }, status=status.HTTP_200_OK)
        return Response(
            {"detail": "Chưa thể gửi email lúc này. Vui lòng thử lại sau."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


class ResetPasswordConfirmView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        ok = auth_service.reset_password_confirm(
            email=data["email"],
            token=data["reset_token"],
            new_password=data["new_password"]
        )
        if not ok:
            return Response(
                {"detail": "Liên kết đặt lại mật khẩu không hợp lệ hoặc đã hết hạn."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {"detail": "Đặt lại mật khẩu thành công."},
            status=status.HTTP_200_OK,
        )

# ---------- Custom reset password confirm ----------
class AdvancedPasswordResetConfirmView(PasswordResetConfirmView):
    """
    View này kế thừa view gốc và tùy chỉnh lại hàm post
    để tự động lấy 'uid' và 'token' từ URL.
    """
    def post(self, request, *args, **kwargs):
        # Lấy data từ body (chứa 'new_password1' và 'new_password2')
        data = request.data.copy()

        # Lấy 'uidb64' và 'token' từ URL (do re_path bắt được) và "auto-fill" vào data.
        # Serializer mong đợi tên là 'uid' và 'token'
        data['uid'] = self.kwargs['uidb64']
        data['token'] = self.kwargs['token']

        # Khởi tạo serializer với data đã được bổ sung
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save() # Lưu mật khẩu mới
        
        # Trả về response thành công
        return Response({"detail": "Password has been reset with the new password."})



User = get_user_model()
# --- Admin (only)
class AdminLoginAsUserView(APIView):
    """
    An admin-only view to obtain JWT tokens for any user.
    The admin must be authenticated and be a superuser/staff.
    
    Usage: POST /api/login/admin-as/<user_id>/
    """
    # This is crucial: only allow authenticated admin users
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    def post(self, request, user_id, *args, **kwargs):
        """
        Takes a user_id from the URL and returns access/refresh tokens
        for that user.
        """
        # Find the user we want to log in as
        # get_object_or_404 will automatically return a 404 response if user not found
        try:
            user_to_login = get_object_or_404(User, pk=user_id)
        except Exception:
             return Response(
                {"error": f"User with ID {user_id} not found."}, 
                status=status.HTTP_404_NOT_FOUND
            )
            
        # Generate tokens for the specified user
        refresh = RefreshToken.for_user(user_to_login)
        session_tracking.register_session(
            user=user_to_login,
            refresh=refresh,
            request=request,
        )
             
        try:
            # Validate the Django user model against the Pydantic DTO
            user_data_dto = UserAdminOutput.model_validate(user_to_login)
            # Use your existing method to get the dictionary
            user_data_dict = user_data_dto.to_dict(exclude_none=True)
        except Exception as e:
            # Catch errors if your User model doesn't match the DTO
            return Response(
                {"error": f"Failed to serialize user data: {e}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        response_data = {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user': user_data_dict  # <-- Use the dictionary from the DTO
        }
        
        return Response(response_data, status=status.HTTP_200_OK)
    

class AdminRefreshUserAccessView(APIView):
    """
    An admin-only view to obtain a new *access token* for any user.
    This does NOT generate a new refresh token.
    
    Usage: POST /api/admin/refresh-access/<user_id>/
    """
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    def post(self, request, user_id, *args, **kwargs):
        """
        Takes a user_id from the URL and returns a new access token
        for that user, along with the user's data.
        """
        try:
            user_to_refresh = get_object_or_404(User, pk=user_id)
        except Exception:
            return Response(
                {"error": f"User with ID {user_id} not found."}, 
                status=status.HTTP_404_NOT_FOUND
            )
            
        # Generate an access token
        access = AccessToken.for_user(user_to_refresh)
        
        # Serialize user data using Pydantic DTO
        try:
            # Validate the Django user model against the Pydantic DTO
            user_data_dto = UserAdminOutput.model_validate(user_to_refresh)
            # Use method to get the dictionary
            user_data_dict = user_data_dto.to_dict(exclude_none=True)
        except Exception as e:
            # Catch errors if your User model doesn't match the DTO
            return Response(
                {"error": f"Failed to serialize user data: {e}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # 3. Format the response as requested
        response_data = {
            'access': str(access),
            'user': user_data_dict  # <-- Use the dictionary from the DTO
        }
        
        return Response(response_data, status=status.HTTP_200_OK)
    

class AdminLogoutUserView(APIView):
    """
    An admin-only view to force-logout any user by blacklisting
    all of their outstanding refresh tokens.
    
    Usage: POST /api/admin/logout-user/<user_id>/
    """
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    def post(self, request, user_id, *args, **kwargs):
        """
        Takes a user_id from the URL and blacklists all of their
        refresh tokens.
        """
        try:
            user_to_logout = get_object_or_404(User, pk=user_id)
        except Exception:
            return Response(
                {"error": f"User with ID {user_id} not found."}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Find all outstanding refresh tokens for the user
        # OutstandingToken only stores refresh tokens
        tokens = OutstandingToken.objects.filter(user=user_to_logout)
        
        # Blacklist each token
        count = 0
        for token in tokens:
            # get_or_create ensures we don't add duplicate entries
            _, created = BlacklistedToken.objects.get_or_create(token=token)
            if created:
                count += 1
        
        return Response(
            {"detail": f"Successfully logged out user {user_to_logout.username}. Blacklisted {count} refresh token(s)."},
            status=status.HTTP_200_OK
        )
    

    



    
