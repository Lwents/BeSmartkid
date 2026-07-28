import pytest
from rest_framework.test import APIClient

from activities.models import Notification
from custom_account.models import UserModel


@pytest.mark.django_db
def test_student_notification_unread_count_is_not_limited_by_page_size():
    student = UserModel.objects.create_user(
        username="notification-student",
        email="notification-student@example.com",
        password="password123",
        role="student",
    )
    for index in range(25):
        Notification.objects.create(
            user=student,
            title=f"Thông báo {index}",
            message="Nội dung kiểm thử",
            category="admin_broadcast",
            is_read=index < 3,
        )
    client = APIClient()
    client.force_authenticate(student)

    response = client.get("/api/student/notifications/?limit=1", HTTP_HOST="localhost")

    assert response.status_code == 200
    assert len(response.data["notifications"]) == 1
    assert response.data["unread_count"] == 22


@pytest.mark.django_db
def test_student_notification_read_actions_only_change_current_student():
    student = UserModel.objects.create_user(
        username="notification-reader",
        email="notification-reader@example.com",
        password="password123",
        role="student",
    )
    other_student = UserModel.objects.create_user(
        username="notification-other-student",
        email="notification-other-student@example.com",
        password="password123",
        role="student",
    )
    first = Notification.objects.create(
        user=student,
        title="Thông báo thứ nhất",
        message="Nội dung",
        category="admin_broadcast",
    )
    Notification.objects.create(
        user=student,
        title="Thông báo thứ hai",
        message="Nội dung",
        category="admin_broadcast",
    )
    other_notification = Notification.objects.create(
        user=other_student,
        title="Thông báo người khác",
        message="Không được thay đổi",
        category="admin_broadcast",
    )
    client = APIClient()
    client.force_authenticate(student)

    initial = client.get("/api/student/notifications/?limit=1", HTTP_HOST="localhost")
    read_one = client.patch(
        f"/api/student/notifications/{first.id}/read/",
        {},
        format="json",
        HTTP_HOST="localhost",
    )
    after_one = client.get("/api/student/notifications/?limit=1", HTTP_HOST="localhost")
    read_all = client.patch(
        "/api/student/notifications/read-all/",
        {},
        format="json",
        HTTP_HOST="localhost",
    )
    after_all = client.get("/api/student/notifications/?limit=1", HTTP_HOST="localhost")

    assert initial.status_code == 200
    assert initial.data["unread_count"] == 2
    assert read_one.status_code == 200
    assert after_one.data["unread_count"] == 1
    assert read_all.status_code == 200
    assert after_all.data["unread_count"] == 0
    other_notification.refresh_from_db()
    assert other_notification.is_read is False
