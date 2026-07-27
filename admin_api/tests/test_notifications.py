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

    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.data["notifications"]] == [str(visible.id)]
    assert list_response.data["unread_count"] == 1
    assert hidden_read_response.status_code == 404
    assert read_all_response.status_code == 200
    assert read_all_response.data["updated_count"] == 1
    hidden.refresh_from_db()
    visible.refresh_from_db()
    assert hidden.is_read is False
    assert visible.is_read is True
