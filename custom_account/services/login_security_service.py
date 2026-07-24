from datetime import timedelta
from typing import Optional

from django.utils import timezone

from custom_account.models import AuthAttempt, SecurityPolicy, UserModel


def get_policy() -> SecurityPolicy:
    return SecurityPolicy.get_current()


def normalize_identifier(identifier: Optional[str]) -> str:
    return (identifier or '').strip().lower()


def get_client_ip(request) -> Optional[str]:
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def is_rate_limited(identifier: str, ip: Optional[str], policy: SecurityPolicy, now=None) -> bool:
    if not policy.rate_limit_login_failures or policy.rate_limit_window_min <= 0:
        return False
    now = now or timezone.now()
    window_start = now - timedelta(minutes=policy.rate_limit_window_min)
    qs = AuthAttempt.objects.filter(success=False, created_at__gte=window_start)
    if identifier:
        qs = qs.filter(username_or_email=identifier)
    elif ip:
        qs = qs.filter(ip_address=ip)
    return qs.count() >= policy.rate_limit_login_failures


def record_attempt(
    *,
    user: Optional[UserModel],
    identifier: str,
    success: bool,
    ip: Optional[str],
    user_agent: str,
    error: str = '',
):
    AuthAttempt.objects.create(
        user=user,
        username_or_email=identifier,
        success=success,
        ip_address=ip,
        user_agent=user_agent or '',
        error=error or '',
    )


def reset_failures(user: UserModel):
    if user.failed_login_count or user.last_failed_login_at or user.lockout_until:
        user.failed_login_count = 0
        user.last_failed_login_at = None
        user.lockout_until = None
        user.save(update_fields=['failed_login_count', 'last_failed_login_at', 'lockout_until'])


def register_failure(user: Optional[UserModel], policy: SecurityPolicy, now=None) -> bool:
    if not user:
        return False
    now = now or timezone.now()
    reset_window = timedelta(minutes=policy.rate_limit_window_min or 10)
    if user.last_failed_login_at and now - user.last_failed_login_at > reset_window:
        user.failed_login_count = 0

    user.failed_login_count += 1
    user.last_failed_login_at = now

    lockout_triggered = False
    update_fields = ['failed_login_count', 'last_failed_login_at']

    if user.failed_login_count >= policy.lockout_attempts:
        lockout_triggered = True
        user.failed_login_count = 0
        user.lockout_until = now + timedelta(minutes=policy.lockout_minutes)
        user.lockout_strikes += 1
        update_fields.extend(['failed_login_count', 'lockout_until', 'lockout_strikes'])

        if user.lockout_strikes >= policy.lockout_ban_strikes:
            user.is_active = False
            user.lockout_until = None
            update_fields.extend(['is_active', 'lockout_until'])

    user.save(update_fields=list(dict.fromkeys(update_fields)))
    return lockout_triggered


def is_twofa_required(user: UserModel, policy: SecurityPolicy) -> bool:
    role = (user.role or '').lower()
    is_admin = user.is_staff or role == 'admin'
    is_teacher = role in ('instructor', 'teacher')
    if is_admin and policy.twofa_enforce_admin:
        return True
    if is_teacher and policy.twofa_enforce_teacher:
        return True
    return False
