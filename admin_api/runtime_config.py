from copy import deepcopy

from django.conf import settings
from django.core.cache import cache
from django.db import DatabaseError, OperationalError, ProgrammingError

from admin_api.models import SystemConfiguration


CACHE_KEY = 'admin_api.runtime_config.v1'
CACHE_SECONDS = 30


def _merge(base, patch):
    result = deepcopy(base)
    for key, value in (patch or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def _defaults():
    return {
        'brand': {'siteName': getattr(settings, 'SITE_NAME', 'SmartKid')},
        'domainEmail': {
            'smtp': {
                'host': getattr(settings, 'EMAIL_HOST', ''),
                'port': getattr(settings, 'EMAIL_PORT', 587),
                'username': getattr(settings, 'EMAIL_HOST_USER', ''),
                'senderName': getattr(settings, 'DEFAULT_FROM_NAME', ''),
                'fromEmail': getattr(settings, 'DEFAULT_FROM_EMAIL', ''),
            },
        },
    }


def get_runtime_config():
    cached = cache.get(CACHE_KEY)
    if isinstance(cached, dict):
        return cached
    data = {}
    try:
        data = SystemConfiguration.objects.filter(pk=1).values_list('data', flat=True).first() or {}
    except (DatabaseError, OperationalError, ProgrammingError):
        # Migrations, health checks and command startup must still work before this table exists.
        data = {}
    config = _merge(_defaults(), data)
    cache.set(CACHE_KEY, config, CACHE_SECONDS)
    return config


def invalidate_runtime_config():
    cache.delete(CACHE_KEY)


def email_settings():
    smtp = get_runtime_config().get('domainEmail', {}).get('smtp', {})
    return {
        'host': str(smtp.get('host') or getattr(settings, 'EMAIL_HOST', '')).strip(),
        'port': int(smtp.get('port') or getattr(settings, 'EMAIL_PORT', 587)),
        'username': str(smtp.get('username') or getattr(settings, 'EMAIL_HOST_USER', '')).strip(),
        # Passwords are never persisted in the admin JSON; they remain server secrets.
        'password': getattr(settings, 'EMAIL_HOST_PASSWORD', ''),
        'sender_name': str(smtp.get('senderName') or '').strip(),
        'from_email': str(
            smtp.get('fromEmail') or getattr(settings, 'DEFAULT_FROM_EMAIL', '')
        ).strip(),
    }


def site_name():
    return str(
        get_runtime_config().get('brand', {}).get('siteName')
        or getattr(settings, 'SITE_NAME', 'SmartKid')
    ).strip()


def timezone_name():
    return str(
        get_runtime_config().get('brand', {}).get('timezone')
        or getattr(settings, 'TIME_ZONE', 'Asia/Ho_Chi_Minh')
    ).strip()


def frontend_base_url():
    domain_email = get_runtime_config().get('domainEmail', {})
    domain = str(domain_email.get('domain') or '').strip().rstrip('/')
    if domain and domain not in {'localhost', '127.0.0.1', '0.0.0.0'}:
        if domain.startswith(('http://', 'https://')):
            return domain
        scheme = 'https' if domain_email.get('forceHttps', True) else 'http'
        return f'{scheme}://{domain}'
    return str(getattr(settings, 'FRONTEND_URL', '') or 'http://localhost:5173').rstrip('/')
