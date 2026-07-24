from typing import Optional, List
from django.db import transaction
from django.contrib.auth import get_user_model

from content.models import Lesson, LessonVersion
from content.domains.lesson_version_domain import (
    LessonVersionDomain, CreateLessonVersionDomain,
    UpdateLessonVersionDomain, ChangeVersionStatusDomain
)


User = get_user_model()


class LessonVersionService:
    """Service for managing lesson versions."""

    @transaction.atomic
    def create_version(self, input_data: CreateLessonVersionDomain) -> LessonVersionDomain:
        input_data.validate()
        lesson = Lesson.objects.get(id=input_data.lesson_id)
        author = User.objects.filter(id=input_data.author_id).first()
        latest_version = lesson.versions.aggregate(max_v=input_data.Max("version"))["max_v"] or 0
        version = LessonVersion.objects.create(
            lesson=lesson,
            version=latest_version + 1,
            status="draft",
            author=author,
            content=input_data.content
        )
        return LessonVersionDomain.from_model(version)

    def list_versions(self, lesson_id: str) -> List[LessonVersionDomain]:
        return [LessonVersionDomain.from_model(v) for v in LessonVersion.objects.filter(lesson_id=lesson_id)]

    @transaction.atomic
    def update_version(self, version_id: str, update_data: UpdateLessonVersionDomain) -> Optional[LessonVersionDomain]:
        try:
            version = LessonVersion.objects.get(id=version_id)
        except LessonVersion.DoesNotExist:
            return None
        update_data.validate()
        version.content.update(update_data.content)
        version.save()
        return LessonVersionDomain.from_model(version)

    @transaction.atomic
    def change_status(self, version_id: str, status_data: ChangeVersionStatusDomain) -> Optional[LessonVersionDomain]:
        try:
            version = LessonVersion.objects.get(id=version_id)
        except LessonVersion.DoesNotExist:
            return None
        status_data.validate()
        version.status = status_data.status
        version.save()
        return LessonVersionDomain.from_model(version)
