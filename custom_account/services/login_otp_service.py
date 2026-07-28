import random
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from django.contrib.auth.hashers import make_password, check_password

from custom_account.models import LoginOTP, UserModel
from infrastructure.email_service import get_email_service, render_email_template
from admin_api.runtime_config import site_name


OTP_EXP_MINUTES = getattr(settings, 'LOGIN_OTP_EXPIRE_MINUTES', 5)
OTP_RESEND_SECONDS = getattr(settings, 'LOGIN_OTP_RESEND_SECONDS', 60)
OTP_MAX_ATTEMPTS = getattr(settings, 'LOGIN_OTP_MAX_ATTEMPTS', 5)


class OTPThrottleError(Exception):
    """Raised when user requests OTP too frequently."""


class OTPExpiredError(Exception):
    pass


class OTPInvalidError(Exception):
    pass


class OTPAttemptsExceededError(Exception):
    pass


class OTPNotFoundError(Exception):
    pass


def _generate_code() -> str:
    return f"{random.randint(0, 999999):06d}"


def request_login_otp(user: UserModel) -> None:
    now = timezone.now()
    existing = LoginOTP.objects.filter(user=user, is_used=False).order_by('-created_at').first()
    if existing and not existing.is_expired and (now - existing.created_at).total_seconds() < OTP_RESEND_SECONDS:
        raise OTPThrottleError("OTP recently sent. Please wait before requesting again.")

    code = _generate_code()
    LoginOTP.objects.create(
        user=user,
        code_hash=make_password(code),
        expires_at=now + timedelta(minutes=OTP_EXP_MINUTES),
    )

    subject = "Mã OTP đăng nhập"
    message = (
        f"Xin chào {user.username or user.email},\n\n"
        f"Mã OTP đăng nhập của bạn là: {code}.\n"
        f"Mã sẽ hết hạn sau {OTP_EXP_MINUTES} phút.\n\n"
        "Nếu bạn không yêu cầu, hãy bỏ qua email này và không chia sẻ mã cho bất kỳ ai."
    )
    brand = site_name()
    support_email = getattr(settings, 'SUPPORT_EMAIL', getattr(settings, 'DEFAULT_FROM_EMAIL', 'support@smartkid.vn'))
    html_body = render_email_template(
        'emails/gmail_base.html',
        {
            'subject': subject,
            'brand': brand,
            'salutation': f"Xin chào {user.username or user.email},",
            'title': "Xác nhận đăng nhập",
            'intro': "Bạn đang đăng nhập vào hệ thống. Nhập mã bên dưới để hoàn tất.",
            'body_lines': [
                f"Mã có hiệu lực trong {OTP_EXP_MINUTES} phút.",
                "Nếu không phải bạn, hãy bỏ qua email này.",
            ],
            'highlight_label': "Mã OTP",
            'highlight_text': code,
            'footer_note': "Vì lí do bảo mật, đừng chia sẻ mã cho bất kỳ ai.",
            'support_email': support_email,
            'preheader': f"Mã OTP có hiệu lực {OTP_EXP_MINUTES} phút.",
        },
    )
    default_sender = getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@example.com')
    email_service = get_email_service()
    email_service.send(user.email, subject, message, html_body=html_body, from_email=default_sender)


def verify_login_otp(user: UserModel, code: str) -> LoginOTP:
    otp = LoginOTP.objects.filter(user=user, is_used=False).order_by('-created_at').first()
    if not otp:
        raise OTPNotFoundError("Không tìm thấy OTP. Vui lòng yêu cầu mã mới.")

    if otp.is_expired:
        otp.is_used = True
        otp.save(update_fields=['is_used'])
        raise OTPExpiredError("OTP đã hết hạn. Vui lòng yêu cầu mã mới.")

    if otp.attempts >= OTP_MAX_ATTEMPTS:
        otp.is_used = True
        otp.save(update_fields=['is_used'])
        raise OTPAttemptsExceededError("Bạn đã nhập sai OTP quá số lần cho phép.")

    if not check_password(code, otp.code_hash):
        otp.attempts += 1
        otp.save(update_fields=['attempts'])
        raise OTPInvalidError("OTP không chính xác.")

    otp.is_used = True
    otp.save(update_fields=['is_used'])
    return otp
