import pytest
from rest_framework.test import APIClient

from content.models import Course, Lesson, Module, Subject
from custom_account.models import UserModel


def _user(username, role, *, staff=False):
    return UserModel.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="QaPass1234",
        role=role,
        is_staff=staff,
    )


@pytest.mark.django_db
def test_students_cannot_create_or_mutate_teacher_content():
    teacher = _user("content-owner", "instructor")
    other_teacher = _user("content-other-teacher", "instructor")
    student = _user("content-student", "student")
    subject = Subject.objects.create(title="Toán phân quyền", slug="toan-phan-quyen")
    course = Course.objects.create(
        subject=subject,
        title="Khóa riêng của giáo viên",
        owner=teacher,
        published=False,
    )
    module = Module.objects.create(course=course, title="Chương riêng", position=0)

    student_client = APIClient()
    student_client.force_authenticate(student)
    assert student_client.post(
        "/api/content/courses/", {"title": "Khóa trái phép"}, format="json"
    ).status_code == 403
    assert student_client.post(
        f"/api/content/courses/{course.id}/modules/",
        {"title": "Chương trái phép", "position": 1},
        format="json",
    ).status_code == 403
    assert student_client.post(
        f"/api/content/modules/{module.id}/lessons/",
        {"title": "Bài trái phép", "position": 1, "content_type": "text"},
        format="json",
    ).status_code == 403
    assert student_client.post(
        f"/api/content/courses/{course.id}/publish/",
        {"published": False},
        format="json",
    ).status_code == 403

    other_teacher_client = APIClient()
    other_teacher_client.force_authenticate(other_teacher)
    assert other_teacher_client.post(
        f"/api/content/courses/{course.id}/publish/",
        {"published": True},
        format="json",
    ).status_code == 403

    course.refresh_from_db()
    assert course.published is False
    assert not Course.objects.filter(title="Khóa trái phép").exists()
    assert not Module.objects.filter(title="Chương trái phép").exists()
    assert not Lesson.objects.filter(title="Bài trái phép").exists()


@pytest.mark.django_db
def test_draft_course_structure_and_lessons_are_not_public():
    teacher = _user("draft-owner", "instructor")
    outsider = _user("draft-outsider", "student")
    course = Course.objects.create(
        title="Khóa đang soạn", owner=teacher, published=False
    )
    module = Module.objects.create(course=course, title="Chương đang soạn", position=0)
    lesson = Lesson.objects.create(
        module=module,
        title="Bài bí mật",
        position=0,
        content_type="text",
        text_content="Nội dung chưa công khai",
        published=False,
    )

    anonymous = APIClient()
    assert anonymous.get(
        f"/api/content/courses/{course.id}/modules/"
    ).status_code == 403
    assert anonymous.get(
        f"/api/content/modules/{module.id}/lessons/"
    ).status_code == 403

    outsider_client = APIClient()
    outsider_client.force_authenticate(outsider)
    assert outsider_client.get(
        f"/api/content/lessons/{lesson.id}/"
    ).status_code == 403

    owner_client = APIClient()
    owner_client.force_authenticate(teacher)
    assert owner_client.get(
        f"/api/content/courses/{course.id}/modules/"
    ).status_code == 200
    assert owner_client.get(
        f"/api/content/modules/{module.id}/lessons/"
    ).status_code == 200


@pytest.mark.django_db
def test_public_course_only_exposes_published_lessons_to_learners():
    teacher = _user("public-owner", "instructor")
    student = _user("public-student", "student")
    course = Course.objects.create(title="Khóa công khai", owner=teacher, published=True)
    module = Module.objects.create(course=course, title="Chương 1", position=0)
    Lesson.objects.create(
        module=module, title="Bài đã mở", position=0, published=True
    )
    Lesson.objects.create(
        module=module, title="Bài đang soạn", position=1, published=False
    )

    client = APIClient()
    client.force_authenticate(student)
    response = client.get(f"/api/content/modules/{module.id}/lessons/")

    assert response.status_code == 200
    titles = [item["title"] for item in response.data["results"]]
    assert titles == ["Bài đã mở"]


@pytest.mark.django_db
def test_course_owner_can_hide_and_republish_lesson_from_editor():
    teacher = _user("lesson-editor-owner", "instructor")
    course = Course.objects.create(title="Khóa sửa bài", owner=teacher, published=True)
    module = Module.objects.create(course=course, title="Chương 1", position=0)
    lesson = Lesson.objects.create(
        module=module, title="Bài có thể ẩn", position=0, published=True
    )
    client = APIClient()
    client.force_authenticate(teacher)

    hidden = client.patch(
        f"/api/content/lessons/{lesson.id}/",
        {"published": False},
        format="json",
    )
    assert hidden.status_code == 200
    lesson.refresh_from_db()
    assert lesson.published is False

    republished = client.patch(
        f"/api/content/lessons/{lesson.id}/",
        {"published": True},
        format="json",
    )
    assert republished.status_code == 200
    lesson.refresh_from_db()
    assert lesson.published is True
