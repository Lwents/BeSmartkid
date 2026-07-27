import pytest
from rest_framework.test import APIClient

from activities.models import Notification
from custom_account.models import UserModel


@pytest.mark.django_db
def test_teacher_notification_unread_count_tracks_read_actions():
    teacher = UserModel.objects.create_user(
        username="notification-teacher",
        email="notification-teacher@example.com",
        password="password123",
        role="instructor",
    )
    other_teacher = UserModel.objects.create_user(
        username="notification-other-teacher",
        email="notification-other-teacher@example.com",
        password="password123",
        role="instructor",
    )
    first = Notification.objects.create(
        user=teacher,
        title="Học sinh hỏi bài",
        message="Câu hỏi thứ nhất",
        category="lesson_question",
    )
    Notification.objects.create(
        user=teacher,
        title="Học sinh hỏi bài",
        message="Câu hỏi thứ hai",
        category="lesson_question",
    )
    other_notification = Notification.objects.create(
        user=other_teacher,
        title="Thông báo của giáo viên khác",
        message="Không được thay đổi",
        category="system",
    )
    client = APIClient()
    client.force_authenticate(teacher)

    initial = client.get("/api/teacher/notifications/?limit=1", HTTP_HOST="localhost")
    read_one = client.patch(
        f"/api/teacher/notifications/{first.id}/read/",
        {},
        format="json",
        HTTP_HOST="localhost",
    )
    after_one = client.get("/api/teacher/notifications/?limit=1", HTTP_HOST="localhost")
    read_all = client.patch(
        "/api/teacher/notifications/read-all/",
        {},
        format="json",
        HTTP_HOST="localhost",
    )
    after_all = client.get("/api/teacher/notifications/?limit=1", HTTP_HOST="localhost")

    assert initial.status_code == 200
    assert len(initial.data["notifications"]) == 1
    assert initial.data["unread_count"] == 2
    assert read_one.status_code == 200
    assert after_one.data["unread_count"] == 1
    assert read_all.status_code == 200
    assert after_all.data["unread_count"] == 0
    other_notification.refresh_from_db()
    assert other_notification.is_read is False
