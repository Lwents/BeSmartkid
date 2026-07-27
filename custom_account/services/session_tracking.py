from datetime import datetime, timezone as datetime_timezone

from django.core.cache import cache
from django.utils import timezone

from custom_account.models import UserPresence, UserSession
from custom_account.services.login_security_service import get_client_ip


def _device_name(user_agent: str) -> str:
    value = (user_agent or '').lower()
    platform = 'Android' if 'android' in value else (
        'Windows' if 'windows' in value else (
            'iPhone/iPad' if 'iphone' in value or 'ipad' in value else 'Thiết bị khác'
        )
    )
    browser = 'Chrome' if 'chrome' in value else (
        'Firefox' if 'firefox' in value else (
            'Safari' if 'safari' in value else 'SmartKid'
        )
    )
    return f'{platform} • {browser}'


def register_session(*, user, refresh, request) -> UserSession:
    now = timezone.now()
    user_agent = request.META.get('HTTP_USER_AGENT', '') if request else ''
    ip_address = get_client_ip(request) if request else None
    expires_at = datetime.fromtimestamp(int(refresh['exp']), tz=datetime_timezone.utc)
    session, _ = UserSession.objects.update_or_create(
        jti=str(refresh['jti']),
        defaults={
            'user': user,
            'device': _device_name(user_agent),
            'ip_address': ip_address,
            'user_agent': user_agent,
            'created_at': now,
            'last_active_at': now,
            'expires_at': expires_at,
            'revoked_at': None,
        },
    )
    _update_presence(user, ip_address, user_agent, now)
    return session


def touch_presence(*, user, request) -> None:
    if not user or not getattr(user, 'is_authenticated', False):
        return
    cache_key = f'user-presence-touch:{user.pk}'
    if cache.get(cache_key):
        return
    cache.set(cache_key, True, timeout=30)
    now = timezone.now()
    user_agent = request.META.get('HTTP_USER_AGENT', '') if request else ''
    ip_address = get_client_ip(request) if request else None
    _update_presence(user, ip_address, user_agent, now)
    session = UserSession.objects.filter(
        user=user,
        revoked_at__isnull=True,
        expires_at__gt=now,
    ).order_by('-created_at').first()
    if session:
        session.last_active_at = now
        session.save(update_fields=['last_active_at'])


def _update_presence(user, ip_address, user_agent, now) -> None:
    UserPresence.objects.update_or_create(
        user=user,
        defaults={
            'last_seen_at': now,
            'ip_address': ip_address,
            'user_agent': user_agent or '',
        },
    )
