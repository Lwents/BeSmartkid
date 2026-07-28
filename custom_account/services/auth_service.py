from urllib.parse import quote

from django.conf import settings
from django.utils import timezone
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.exceptions import ValidationError

from custom_account.models import UserModel
from infrastructure.email_service import get_email_service, render_email_template
from admin_api.runtime_config import frontend_base_url, site_name



token_generator = PasswordResetTokenGenerator()

# password reset flow
def reset_password_request(email: str) -> None:
    """
    Generate a reset token and trigger email sending.
    """
    try:
        user = UserModel.objects.get(email=email)
    except UserModel.DoesNotExist:
        raise ValueError("User not found")

    token = token_generator.make_token(user)
    frontend_base = frontend_base_url()
    reset_link = f"{frontend_base}/auth/reset-password?email={quote(user.email)}&token={quote(token)}"

    try:
        email_service = get_email_service()
        brand = site_name()
        support_email = getattr(
            settings, 'SUPPORT_EMAIL', getattr(settings, 'DEFAULT_FROM_EMAIL', 'support@smartkid.vn')
        )
        subject = "SmartKid - Đặt lại mật khẩu"
        message = (
            f"Xin chào {user.username or user.email},\n\n"
            f"Bạn vừa yêu cầu đặt lại mật khẩu cho tài khoản {brand}.\n"
            f"Nhấn vào liên kết để đặt lại mật khẩu: {reset_link}\n\n"
            "Nếu bạn không yêu cầu, hãy bỏ qua email này."
        )
        html_body = render_email_template(
            'emails/gmail_base.html',
            {
                'subject': subject,
                'brand': brand,
                'title': "Đặt lại mật khẩu",
                'salutation': f"Xin chào {user.username or user.email},",
                'intro': f"Bạn vừa yêu cầu đặt lại mật khẩu cho tài khoản {brand}.",
                'body_lines': [
                    "Nhấn vào nút bên dưới để tạo mật khẩu mới.",
                    "Liên kết chỉ có hiệu lực trong thời gian ngắn để bảo vệ tài khoản của bạn.",
                ],
                'cta_url': reset_link,
                'cta_label': "Đặt lại mật khẩu",
                'footer_note': "Nếu bạn không yêu cầu thao tác này, hãy bỏ qua email hoặc đổi mật khẩu ngay.",
                'support_email': support_email,
                'preheader': "Liên kết đặt lại mật khẩu từ SmartKid.",
            },
        )
        email_service.send(
            to=email,
            subject=subject,
            body=message,
            html_body=html_body,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@example.com'),
        )
        return True
    except Exception as e:
        # Log the actual error for debugging
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to send password reset email to {email}: {str(e)}")
        raise  # Re-raise to let caller handle it


def reset_password_confirm(email: str, token: str, new_password: str) -> bool:
    try:
        user = UserModel.objects.get(email=email)
    except UserModel.DoesNotExist:
        return False

    # Verify token properly
    if not token_generator.check_token(user, token):
        return False

    user.set_password(new_password)
    user.save()
    return True


def is_password_reset_token_valid(email: str, token: str) -> bool:
    if not email or not token:
        return False

    try:
        user = UserModel.objects.get(email=email)
    except UserModel.DoesNotExist:
        return False

    return token_generator.check_token(user, token)


def authenticate_user(username_or_email: str, password: str) -> UserModel:
    """
    Authenticate a user by username or email and password.
    Raises ValidationError if authentication fails.
    Returns the authenticated User object.
    """
    user = UserModel.objects.filter(username=username_or_email).first() or \
            UserModel.objects.filter(email=username_or_email).first()
    if (
        user is None
        or not user.check_password(password)
        or not user.is_active
        or (user.lockout_until and user.lockout_until > timezone.now())
    ):
        raise ValidationError("No active account found with the given credentials")
    return user
