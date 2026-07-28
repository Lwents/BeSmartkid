import pytest
from rest_framework.test import APIClient

from activities.models import Notification
from custom_account.models import UserModel


@pytest.mark.django_db
def test_admin_notification_api_hides_teacher_question_categories():
    admin = UserModel.objects.create_user(
        username="notification-admin",
        email="notification-admin@example.com",
        password="password123",
        role="admin",
        is_staff=True,
    )
    hidden = Notification.objects.create(
        user=admin,
        title="Học sinh hỏi bài",
        message="Câu hỏi chỉ dành cho giáo viên",
        category="lesson_question",
    )
    visible = Notification.objects.create(
        user=admin,
        title="Thông báo hệ thống",
        message="Nội dung quản trị",
        category="system",
    )
    client = APIClient()
    client.force_authenticate(admin)

    list_response = client.get(
        "/api/admin/notifications/?limit=100",
        HTTP_HOST="localhost",
    )
    hidden_read_response = client.patch(
        f"/api/admin/notifications/{hidden.id}/read/",
        {},
        format="json",
        HTTP_HOST="localhost",
    )
    read_all_response = client.patch(
        "/api/admin/notifications/read-all/",
        {},
        format="json",
        HTTP_HOST="localhost",
    )
    after_read_all = client.get(
        "/api/admin/notifications/?limit=100",
        HTTP_HOST="localhost",
    )

    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.data["notifications"]] == [str(visible.id)]
    assert list_response.data["unread_count"] == 1
    assert hidden_read_response.status_code == 404
    assert read_all_response.status_code == 200
    assert read_all_response.data["updated_count"] == 1
    assert after_read_all.status_code == 200
    assert after_read_all.data["unread_count"] == 0
    hidden.refresh_from_db()
    visible.refresh_from_db()
    assert hidden.is_read is False
    assert visible.is_read is True


@pytest.mark.django_db
def test_admin_can_broadcast_notification_only_to_requested_role():
    admin = UserModel.objects.create_user(
        username='notification-sender', email='sender@example.com',
        password='password123', role='admin', is_staff=True,
    )
    student = UserModel.objects.create_user(
        username='notification-student', email='student@example.com',
        password='password123', role='student',
    )
    teacher = UserModel.objects.create_user(
        username='notification-teacher', email='teacher@example.com',
        password='password123', role='instructor',
    )
    client = APIClient()
    client.force_authenticate(admin)

    response = client.post('/api/admin/notifications/', {
        'title': 'Lịch học mới',
        'message': 'Em hãy mở ứng dụng để xem lịch học tuần này.',
        'audience': 'student',
    }, format='json')

    assert response.status_code == 201
    assert response.data['created_count'] == 1
    assert Notification.objects.filter(
        user=student, category='admin_broadcast', is_read=False,
    ).exists()
    assert not Notification.objects.filter(user=teacher, category='admin_broadcast').exists()
    assert not Notification.objects.filter(user=admin, category='admin_broadcast').exists()


@pytest.mark.django_db
def test_admin_broadcast_all_reaches_active_students_and_teachers_only():
    admin = UserModel.objects.create_user(
        username='broadcast-admin', email='broadcast-admin@example.com',
        password='password123', role='admin', is_staff=True,
    )
    student = UserModel.objects.create_user(
        username='broadcast-student', email='broadcast-student@example.com',
        password='password123', role='student',
    )
    teacher = UserModel.objects.create_user(
        username='broadcast-teacher', email='broadcast-teacher@example.com',
        password='password123', role='instructor',
    )
    inactive_student = UserModel.objects.create_user(
        username='broadcast-inactive', email='broadcast-inactive@example.com',
        password='password123', role='student', is_active=False,
    )
    other_admin = UserModel.objects.create_user(
        username='broadcast-other-admin', email='broadcast-other-admin@example.com',
        password='password123', role='admin', is_staff=True,
    )
    client = APIClient()
    client.force_authenticate(admin)

    response = client.post('/api/admin/notifications/', {
        'title': 'Thông báo chung',
        'message': 'Nội dung dành cho giáo viên và học sinh.',
        'audience': 'all',
    }, format='json')

    assert response.status_code == 201
    assert response.data['created_count'] == 2
    recipients = set(Notification.objects.filter(
        category='admin_broadcast', title='Thông báo chung',
    ).values_list('user_id', flat=True))
    assert recipients == {student.id, teacher.id}
    assert inactive_student.id not in recipients
    assert other_admin.id not in recipients
    assert admin.id not in recipients


@pytest.mark.django_db
def test_admin_broadcast_rejects_empty_and_invalid_input():
    admin = UserModel.objects.create_user(
        username='invalid-broadcast-admin', email='invalid-broadcast@example.com',
        password='password123', role='admin', is_staff=True,
    )
    client = APIClient()
    client.force_authenticate(admin)

    response = client.post('/api/admin/notifications/', {
        'title': '   ',
        'message': '',
        'audience': 'admin',
        'type': 'unknown',
    }, format='json')

    assert response.status_code == 400
    assert set(response.data['errors']) == {'title', 'message', 'audience', 'type'}
    assert not Notification.objects.filter(category='admin_broadcast').exists()


@pytest.mark.django_db
def test_admin_notification_list_is_paginated_without_losing_badge_fields():
    admin = UserModel.objects.create_user(
        username='notification-pages', email='notification-pages@example.com',
        password='password123', role='admin', is_staff=True,
    )
    for index in range(3):
        Notification.objects.create(
            user=admin, title=f'Thông báo {index}', message='Nội dung', category='system'
        )
    client = APIClient()
    client.force_authenticate(admin)

    response = client.get('/api/admin/notifications/?limit=2')

    assert response.status_code == 200
    assert len(response.data['notifications']) == 2
    assert response.data['results'] == response.data['notifications']
    assert response.data['total'] == 3
    assert response.data['unread_count'] == 3
    assert response.data['next']


@pytest.mark.django_db
@pytest.mark.parametrize('limit', ['abc', '0', '-1', '101'])
def test_admin_notifications_reject_invalid_limit(limit):
    admin = UserModel.objects.create_user(
        username=f'limit-admin-{limit}', email=f'limit-{limit}@example.com',
        password='password123', role='admin', is_staff=True,
    )
    client = APIClient()
    client.force_authenticate(admin)

    response = client.get(f'/api/admin/notifications/?limit={limit}')

    assert response.status_code == 400
