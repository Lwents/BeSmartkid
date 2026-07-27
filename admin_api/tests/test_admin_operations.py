from datetime import timedelta
from pathlib import Path

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from admin_api.models import AdminAuditLog, SystemBackup, SystemConfiguration
from custom_account.models import AuthAttempt, UserModel, UserPresence, UserSession


@pytest.fixture
def admin_client():
    admin = UserModel.objects.create_user(
        username='admin-operations',
        email='admin-operations@example.com',
        password='password123',
        role='admin',
        is_staff=True,
    )
    client = APIClient()
    client.force_authenticate(admin)
    return admin, client


@pytest.mark.django_db
def test_active_users_uses_recent_presence_instead_of_login_time(admin_client):
    _admin, client = admin_client
    active = UserModel.objects.create_user(
        username='active-student',
        email='active-student@example.com',
        password='password123',
    )
    stale = UserModel.objects.create_user(
        username='stale-student',
        email='stale-student@example.com',
        password='password123',
    )
    UserPresence.objects.create(user=active, last_seen_at=timezone.now())
    UserPresence.objects.create(
        user=stale,
        last_seen_at=timezone.now() - timedelta(minutes=11),
    )

    response = client.get('/api/admin/dashboard/active-users/')

    assert response.status_code == 200
    assert response.data['count'] == 1
    assert response.data['recent'][0]['email'] == active.email


@pytest.mark.django_db
def test_session_list_and_revoke_use_real_refresh_tokens(admin_client):
    admin, client = admin_client
    refresh = RefreshToken.for_user(admin)
    token = OutstandingToken.objects.get(jti=str(refresh['jti']))
    UserSession.objects.create(
        user=admin,
        jti=token.jti,
        device='Android • SmartKid',
        ip_address='10.0.2.16',
        created_at=token.created_at,
        last_active_at=token.created_at,
        expires_at=token.expires_at,
    )

    listed = client.get('/api/admin/security/sessions/')
    revoked = client.delete(f'/api/admin/security/sessions/{token.jti}/')

    assert listed.status_code == 200
    assert any(item['jti'] == token.jti for item in listed.data)
    assert revoked.status_code == 200
    assert BlacklistedToken.objects.filter(token=token).exists()
    assert UserSession.objects.get(jti=token.jti).revoked_at is not None


@pytest.mark.django_db
def test_system_configuration_is_persisted_and_audited(admin_client):
    admin, client = admin_client
    payload = {'brand': {'siteName': 'SmartKid School'}}

    response = client.post('/api/admin/system/config/', payload, format='json')

    assert response.status_code == 200
    config = SystemConfiguration.objects.get(pk=1)
    assert config.data == payload
    assert config.updated_by == admin
    assert response.data['version'] == 1
    assert AdminAuditLog.objects.filter(action='system.config.update').exists()


@pytest.mark.django_db
def test_backup_endpoint_creates_a_real_compressed_fixture(admin_client, tmp_path):
    _admin, client = admin_client
    with override_settings(MEDIA_ROOT=tmp_path):
        response = client.post(
            '/api/admin/system/backups/',
            {'notes': 'Bản kiểm thử'},
            format='json',
        )

    assert response.status_code == 201
    backup = SystemBackup.objects.get(pk=response.data['id'])
    target = Path(tmp_path) / 'system_backups' / backup.file_name
    assert backup.status == SystemBackup.STATUS_COMPLETED
    assert backup.size_bytes > 0
    assert len(backup.checksum) == 64
    assert target.exists()


@pytest.mark.django_db
def test_activity_log_combines_real_auth_and_admin_events(admin_client):
    admin, client = admin_client
    AuthAttempt.objects.create(
        user=admin,
        username_or_email=admin.email,
        success=True,
        ip_address='127.0.0.1',
    )
    AdminAuditLog.objects.create(
        actor=admin,
        action='user.update',
        target_type='user',
        target_id=admin.id,
    )

    response = client.get('/api/admin/activity-logs/')

    assert response.status_code == 200
    actions = {item['action'] for item in response.data['items']}
    assert {'user.login', 'user.update'} <= actions


@pytest.mark.django_db
def test_invalid_admin_operation_ids_return_client_errors(admin_client):
    _admin, client = admin_client

    activity = client.get('/api/admin/activity-logs/audit:not-a-uuid/')
    restore = client.post(
        '/api/admin/system/restore/',
        {'backupId': 'not-a-uuid'},
        format='json',
    )

    assert activity.status_code == 404
    assert restore.status_code == 400
