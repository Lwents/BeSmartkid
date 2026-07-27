import pytest
from rest_framework.test import APIClient

from content.models import Course, Enrollment, Lesson, LessonProgress, Module, Subject
from custom_account.models import UserModel


@pytest.fixture
def lesson_access_data(db):
    student = UserModel.objects.create_user(
        username="lesson-student",
        email="lesson-student@example.com",
        password="password123",
        role="student",
    )
    teacher = UserModel.objects.create_user(
        username="lesson-teacher",
        email="lesson-teacher@example.com",
        password="password123",
        role="instructor",
    )
    subject = Subject.objects.create(title="Toán", slug="toan-unlock-test")
    course = Course.objects.create(
        subject=subject,
        title="Khóa học tuần tự",
        owner=teacher,
        published=True,
    )
    Enrollment.objects.create(course=course, student=student)

    chapter_one = Module.objects.create(course=course, title="Chương 1", position=1)
    chapter_two = Module.objects.create(course=course, title="Chương 2", position=2)
    chapter_three = Module.objects.create(course=course, title="Chương 3", position=3)
    lessons = {
        "one": Lesson.objects.create(
            module=chapter_one, title="Bài 1", position=1, published=True
        ),
        "two": Lesson.objects.create(
            module=chapter_one, title="Bài 2", position=2, published=True
        ),
        "three": Lesson.objects.create(
            module=chapter_two, title="Bài 3", position=1, published=True
        ),
        "four": Lesson.objects.create(
            module=chapter_three, title="Bài 4", position=1, published=True
        ),
    }
    client = APIClient()
    client.force_authenticate(student)
    return client, student, course, lessons


@pytest.mark.django_db
def test_unlock_check_requires_previous_lesson(lesson_access_data):
    client, student, _, lessons = lesson_access_data

    first_response = client.get(
        f"/api/content/lessons/{lessons['one'].id}/unlock-check/"
    )
    second_response = client.get(
        f"/api/content/lessons/{lessons['two'].id}/unlock-check/"
    )

    assert first_response.status_code == 200
    assert first_response.data["can_unlock"] is True
    assert second_response.status_code == 200
    assert second_response.data["can_unlock"] is False
    assert second_response.data["previous_lesson_id"] == str(lessons["one"].id)

    LessonProgress.objects.create(
        lesson=lessons["one"], student=student, completed=True
    )
    unlocked_response = client.get(
        f"/api/content/lessons/{lessons['two'].id}/unlock-check/"
    )
    assert unlocked_response.data["can_unlock"] is True


@pytest.mark.django_db
def test_next_chapter_requires_every_lesson_in_previous_chapters(lesson_access_data):
    client, student, _, lessons = lesson_access_data
    LessonProgress.objects.create(
        lesson=lessons["two"], student=student, completed=True
    )
    LessonProgress.objects.create(
        lesson=lessons["three"], student=student, completed=True
    )

    chapter_two_response = client.get(
        f"/api/content/lessons/{lessons['three'].id}/unlock-check/"
    )
    chapter_three_response = client.get(
        f"/api/content/lessons/{lessons['four'].id}/unlock-check/"
    )

    assert chapter_two_response.status_code == 200
    assert chapter_two_response.data["can_unlock"] is False
    assert chapter_two_response.data["previous_lesson_id"] == str(lessons["one"].id)
    assert chapter_three_response.data["can_unlock"] is False
    assert chapter_three_response.data["previous_lesson_id"] == str(lessons["one"].id)


@pytest.mark.django_db
def test_player_and_progress_endpoints_reject_locked_lesson(lesson_access_data):
    client, student, course, lessons = lesson_access_data
    locked_player_url = f"/api/student/courses/{course.id}/player/{lessons['two'].id}/"
    locked_progress_url = f"/api/content/lessons/{lessons['two'].id}/progress/"

    assert client.get(locked_player_url).status_code == 403
    assert client.post(locked_progress_url, {"video_watched": True}, format="json").status_code == 403
    assert not LessonProgress.objects.filter(
        lesson=lessons["two"], student=student
    ).exists()

    LessonProgress.objects.create(
        lesson=lessons["one"], student=student, completed=True
    )
    assert client.get(locked_player_url).status_code == 200


@pytest.mark.django_db
def test_course_detail_marks_lessons_unlocked_in_sequence(lesson_access_data):
    client, student, course, lessons = lesson_access_data
    LessonProgress.objects.create(
        lesson=lessons["one"], student=student, completed=True
    )

    response = client.get(f"/api/student/courses/{course.id}/")

    assert response.status_code == 200
    returned_lessons = [
        lesson
        for section in response.data["sections"]
        for lesson in section["lessons"]
    ]
    assert [lesson["unlocked"] for lesson in returned_lessons] == [
        True,
        True,
        False,
        False,
    ]
