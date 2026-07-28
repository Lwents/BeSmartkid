from datetime import timedelta
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from admin_api.models import AdminAuditLog, SystemBackup, SystemConfiguration
from content.models import Course, Enrollment, Lesson, Module, Subject
from custom_account.models import (
    AuthAttempt,
    SecurityPolicy,
    UserModel,
    UserPresence,
    UserSession,
)


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
    assert config.data['brand']['siteName'] == 'SmartKid School'
    assert config.data['brand']['language'] == 'vi'
    assert config.data['authSession']['idleTimeoutMin'] == 30
    assert config.updated_by == admin
    assert response.data['version'] == 1
    assert AdminAuditLog.objects.filter(action='system.config.update').exists()


@pytest.mark.django_db
def test_system_configuration_partial_update_preserves_other_sections(admin_client):
    _admin, client = admin_client
    first = client.post(
        '/api/admin/system/config/',
        {'brand': {'siteName': 'SmartKid School'}},
        format='json',
    )
    second = client.patch(
        '/api/admin/system/config/',
        {'maintenance': {'enabled': True}},
        format='json',
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.data['brand']['siteName'] == 'SmartKid School'
    assert second.data['maintenance']['enabled'] is True
    assert second.data['version'] == 2


@pytest.mark.django_db
def test_system_configuration_removes_legacy_payment_settings(admin_client):
    _admin, client = admin_client
    SystemConfiguration.objects.create(
        pk=1,
        data={
            'brand': {'siteName': 'SmartKid'},
            'integrations': {
                'payments': {'momo': True},
                'zoom': {'enabled': False},
            },
        },
    )

    response = client.get('/api/admin/system/config/')
    rejected = client.patch(
        '/api/admin/system/config/',
        {'integrations': {'payments': {'momo': True}}},
        format='json',
    )

    assert response.status_code == 200
    assert 'payments' not in response.data['integrations']
    assert rejected.status_code == 400
    assert 'integrations.payments' in rejected.data['errors']


@pytest.mark.django_db
def test_system_configuration_rejects_invalid_form_values(admin_client):
    _admin, client = admin_client

    response = client.patch(
        '/api/admin/system/config/',
        {
            'brand': {'siteName': ''},
            'domainEmail': {'smtp': {'port': 70000, 'fromEmail': 'email-sai'}},
            'maintenance': {'window': {'start': '25:90'}},
        },
        format='json',
    )

    assert response.status_code == 400
    assert set(response.data['errors']) == {
        'brand.siteName',
        'domainEmail.smtp.port',
        'domainEmail.smtp.fromEmail',
        'maintenance.window.start',
    }


@pytest.mark.django_db
def test_admin_can_test_saved_email_configuration(admin_client, mocker):
    _admin, client = admin_client
    email_service = mocker.patch(
        'admin_api.views.system_admin_view.get_email_service'
    ).return_value

    response = client.post(
        '/api/admin/system/test-email/',
        {'email': 'receiver@example.com'},
        format='json',
    )

    assert response.status_code == 200
    email_service.send.assert_called_once_with(
        to='receiver@example.com',
        subject='SmartKid - Kiểm tra cấu hình email',
        body='Email máy chủ SmartKid đã được cấu hình và gửi thành công.',
    )
    assert AdminAuditLog.objects.filter(action='system.email.test').exists()


@pytest.mark.django_db
def test_security_policy_updates_false_values_and_is_audited(admin_client):
    _admin, client = admin_client
    SecurityPolicy.objects.create(
        pk=1,
        twofa_enforce_admin=True,
        twofa_enforce_teacher=True,
    )

    response = client.patch(
        '/api/admin/security/policy/',
        {
            'twoFA': {'enforceAdmin': False, 'enforceTeacher': False},
            'rateLimit': {'loginFailures': 7, 'windowMin': 15},
            'lockout': {'attempts': 6, 'lockMinutes': 45, 'banStrikes': 4},
            'rbacNote': 'Chỉ cấp quyền theo nhiệm vụ.',
        },
        format='json',
    )

    assert response.status_code == 200
    policy = SecurityPolicy.get_current()
    assert policy.twofa_enforce_admin is False
    assert policy.twofa_enforce_teacher is False
    assert policy.rate_limit_login_failures == 7
    assert policy.lockout_minutes == 45
    assert AdminAuditLog.objects.filter(action='security.policy.update').exists()


@pytest.mark.django_db
def test_security_policy_rejects_string_booleans_and_out_of_range_numbers(admin_client):
    _admin, client = admin_client

    response = client.post(
        '/api/admin/security/policy/',
        {
            'twoFA': {'enforceAdmin': 'false'},
            'rateLimit': {'loginFailures': 0},
        },
        format='json',
    )

    assert response.status_code == 400
    assert set(response.data['errors']) == {
        'twoFA.enforceAdmin',
        'rateLimit.loginFailures',
    }


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
def test_backup_list_is_paginated(admin_client):
    _admin, client = admin_client
    for index in range(3):
        SystemBackup.objects.create(
            file_name=f'backup-page-{index}.json.gz',
            status=SystemBackup.STATUS_COMPLETED,
            size_bytes=index + 1,
        )

    response = client.get('/api/admin/system/backups/?pageSize=2')

    assert response.status_code == 200
    assert len(response.data['results']) == 2
    assert response.data['count'] == 3
    assert response.data['next']


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
def test_admin_lists_expose_working_next_page_links(admin_client):
    admin, client = admin_client
    for index in range(3):
        UserModel.objects.create_user(
            username=f'page-student-{index}',
            email=f'page-student-{index}@example.com',
            password='password123',
            role='student',
        )
    subject = Subject.objects.create(title='Phân trang', slug='phan-trang-admin')
    for index in range(3):
        Course.objects.create(
            title=f'Khóa phân trang {index}', subject=subject, owner=admin,
        )
        AdminAuditLog.objects.create(
            actor=admin, action=f'pagination.test.{index}', target_type='test',
        )

    users = client.get('/api/account/admin/users/?page=1&pageSize=2')
    courses = client.get('/api/admin/courses/?page=1&pageSize=2')
    activity = client.get('/api/admin/activity-logs/?page=1&pageSize=2')

    for response in (users, courses, activity):
        assert response.status_code == 200
        assert len(response.data['results']) == 2
        assert response.data['next']
        assert response.data['next'].startswith('http://testserver/')


@pytest.mark.django_db
@pytest.mark.parametrize('path', [
    '/api/account/admin/users/?page=abc',
    '/api/account/admin/users/?pageSize=0',
    '/api/admin/courses/?page=-1',
    '/api/admin/courses/?pageSize=101',
    '/api/admin/activity-logs/?pageSize=abc',
])
def test_admin_lists_reject_invalid_pagination(admin_client, path):
    _admin, client = admin_client

    response = client.get(path)

    assert response.status_code == 400


@pytest.mark.django_db
def test_dashboard_uses_latest_persisted_backup(admin_client):
    _admin, client = admin_client
    backup = SystemBackup.objects.create(
        file_name='dashboard-backup.json.gz',
        status=SystemBackup.STATUS_COMPLETED,
        size_bytes=12,
    )

    response = client.get('/api/admin/dashboard/')

    assert response.status_code == 200
    assert response.data['system']['backup']['status'] == SystemBackup.STATUS_COMPLETED
    assert response.data['system']['backup']['lastRun'] == backup.created_at.isoformat()


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


@pytest.mark.django_db
def test_admin_can_view_and_remove_video_without_deleting_lesson(admin_client, tmp_path):
    admin, client = admin_client
    subject = Subject.objects.create(title='Toán', slug='toan-admin-video')
    course = Course.objects.create(
        title='Khóa có video', subject=subject, owner=admin, published=True
    )
    module = Module.objects.create(course=course, title='Chương 1', position=1)

    with override_settings(
        MEDIA_ROOT=tmp_path,
        STORAGES={
            'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        },
    ):
        lesson = Lesson.objects.create(
            module=module,
            title='Video cần kiểm tra',
            position=1,
            content_type='video',
            published=True,
            video_file=SimpleUploadedFile('lesson.mp4', b'video-content'),
            video_transcript='Nội dung video',
        )
        stored_name = lesson.video_file.name
        storage = lesson.video_file.storage
        assert storage.exists(stored_name)

        detail = client.get(f'/api/admin/courses/{course.id}/')
        removed = client.delete(
            f'/api/admin/courses/{course.id}/lessons/{lesson.id}/video/'
        )
        assert not storage.exists(stored_name)

    assert detail.status_code == 200
    assert detail.data['sections'][0]['lessons'][0]['hasVideo'] is True
    assert detail.data['sections'][0]['lessons'][0]['videoSource'] == 'file'
    assert removed.status_code == 200

    lesson.refresh_from_db()
    assert Lesson.objects.filter(pk=lesson.id).exists()
    assert not lesson.video_file
    assert not lesson.video_url
    assert lesson.video_transcript is None
    assert lesson.published is False
    assert AdminAuditLog.objects.filter(
        action='lesson.video.delete', target_id=str(lesson.id)
    ).exists()


@pytest.mark.django_db
def test_admin_cannot_delete_video_through_another_course(admin_client):
    admin, client = admin_client
    subject = Subject.objects.create(title='Tiếng Việt', slug='tv-admin-video')
    source_course = Course.objects.create(title='Khóa nguồn', subject=subject, owner=admin)
    other_course = Course.objects.create(title='Khóa khác', subject=subject, owner=admin)
    module = Module.objects.create(course=source_course, title='Chương', position=1)
    lesson = Lesson.objects.create(
        module=module,
        title='Video',
        content_type='video',
        video_url='https://example.com/video.mp4',
    )

    response = client.delete(
        f'/api/admin/courses/{other_course.id}/lessons/{lesson.id}/video/'
    )

    assert response.status_code == 404
    lesson.refresh_from_db()
    assert lesson.video_url == 'https://example.com/video.mp4'


@pytest.mark.django_db
def test_admin_can_delete_course_but_cannot_change_publication_state(admin_client):
    admin, client = admin_client
    subject = Subject.objects.create(title='Khoa học', slug='science-admin-state')
    course = Course.objects.create(title='Khóa cần quản lý', subject=subject, owner=admin)
    course_id = str(course.id)
    module = Module.objects.create(course=course, title='Chương cần xóa', position=1)
    Lesson.objects.create(module=module, title='Bài cần xóa', position=1)
    student = UserModel.objects.create(
        username='course-delete-student',
        email='course-delete-student@example.com',
        role='student',
    )
    Enrollment.objects.create(course=course, student=student)

    detail = client.get(f'/api/admin/courses/{course.id}/')
    removed_actions = [
        client.post(f'/api/admin/courses/{course.id}/{action}/')
        for action in (
            'approve', 'reject', 'publish', 'unpublish', 'archive', 'restore'
        )
    ]
    delete_course = client.delete(f'/api/admin/courses/{course.id}/')

    assert detail.status_code == 200
    assert all(response.status_code == 404 for response in removed_actions)
    assert delete_course.status_code == 200
    assert delete_course.data['courseId'] == course_id
    assert not Course.objects.filter(id=course_id).exists()
    assert not Module.objects.filter(id=module.id).exists()
    assert not Enrollment.objects.filter(course_id=course_id).exists()
    assert AdminAuditLog.objects.filter(
        action='course.delete', target_type='course', target_id=course_id,
        actor=admin,
    ).exists()


@pytest.mark.django_db
def test_admin_can_change_user_role_and_cannot_demote_self(admin_client):
    admin, client = admin_client
    target = UserModel.objects.create_user(
        username='role-target',
        email='role-target@example.com',
        password='StartPass123!',
        role='student',
    )
    other_admin = UserModel.objects.create_user(
        username='other-admin',
        email='other-admin@example.com',
        password='StartPass123!',
        role='admin',
        is_staff=True,
    )

    listed = client.get('/api/account/admin/users/?page=1&pageSize=100')
    changed_teacher = client.patch(
        f'/api/account/admin/users/{target.id}/',
        {'role': 'instructor'},
        format='json',
    )
    changed_admin = client.patch(
        f'/api/account/admin/users/{target.id}/',
        {'role': 'admin'},
        format='json',
    )
    self_demote = client.patch(
        f'/api/account/admin/users/{admin.id}/',
        {'role': 'student'},
        format='json',
    )

    listed_ids = {item['id'] for item in listed.data['results']}
    assert target.id in listed_ids
    assert other_admin.id in listed_ids
    assert admin.id not in listed_ids
    assert changed_teacher.status_code == 200
    assert changed_admin.status_code == 200
    target.refresh_from_db()
    assert target.role == 'admin'
    assert target.is_staff is True
    assert self_demote.status_code == 400
    admin.refresh_from_db()
    assert admin.role == 'admin'
    assert admin.is_staff is True
    assert AdminAuditLog.objects.filter(
        action='user.update', target_id=str(target.id)
    ).count() == 2


@pytest.mark.django_db
def test_regular_user_cannot_promote_self_through_profile_api():
    user = UserModel.objects.create_user(
        username='self-role-target',
        email='self-role-target@example.com',
        password='StartPass123!',
        role='student',
    )
    client = APIClient()
    client.force_authenticate(user)

    response = client.patch(
        '/api/account/user/',
        {'role': 'admin'},
        format='json',
    )

    assert response.status_code == 400
    user.refresh_from_db()
    assert user.role == 'student'
    assert user.is_staff is False


@pytest.mark.django_db
def test_admin_password_reset_revokes_sessions_and_is_audited(admin_client):
    _admin, client = admin_client
    target = UserModel.objects.create_user(
        username='password-target',
        email='password-target@example.com',
        password='StartPass123!',
        role='student',
    )
    refresh = RefreshToken.for_user(target)
    token = OutstandingToken.objects.get(jti=str(refresh['jti']))
    session = UserSession.objects.create(
        user=target,
        jti=token.jti,
        device='Android test',
        created_at=token.created_at,
        last_active_at=token.created_at,
        expires_at=token.expires_at,
    )

    weak = client.post(
        f'/api/account/admin/password/set/{target.id}/',
        {'new_password': '123'},
        format='json',
    )
    reset = client.post(
        f'/api/account/admin/password/set/{target.id}/',
        {'new_password': 'NewSecurePass123!'},
        format='json',
    )

    assert weak.status_code == 400
    assert reset.status_code == 200
    target.refresh_from_db()
    session.refresh_from_db()
    assert target.check_password('NewSecurePass123!')
    assert session.revoked_at is not None
    assert BlacklistedToken.objects.filter(token=token).exists()
    assert AdminAuditLog.objects.filter(
        action='user.password.reset', target_id=str(target.id)
    ).exists()
