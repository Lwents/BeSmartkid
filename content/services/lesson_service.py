from typing import List, Optional
from django.db import transaction
from django.contrib.auth import get_user_model

from content.models import Lesson, Module, LessonVersion
from content.domains.lesson_domain import (
    LessonDomain, CreateLessonDomain, UpdateLessonDomain, PublishLessonDomain, ReorderLessonsDomain
)
from content.domains.lesson_version_domain import CreateLessonVersionDomain

User = get_user_model()


class LessonService:
    """Service for managing lessons inside modules."""

    @transaction.atomic
    def create_lesson(self, input_data: CreateLessonDomain, author_id: Optional[int] = None) -> LessonDomain:
        input_data.validate()
        module = Module.objects.get(id=input_data.module_id)
        # Mặc định published = True để tiện cho giáo viên
        lesson = Lesson.objects.create(
            module=module,
            title=input_data.title,
            position=input_data.position,
            content_type=input_data.content_type,
            published=True  # Mặc định xuất bản ngay
        )
        
        # Tự động tạo LessonVersion với status="published" để đảm bảo course có thể publish
        # Tạo version với content structure tối thiểu (có thể thêm content blocks sau)
        author = User.objects.filter(id=author_id).first() if author_id else None
        LessonVersion.objects.create(
            lesson=lesson,
            version=1,
            status='published',  # Mặc định published
            author=author,
            content={"structure": "lesson", "content_blocks": []}  # Content structure tối thiểu
        )
        
        return LessonDomain.from_model(lesson)

    def list_lessons(self, module_id: str) -> List[LessonDomain]:
        return [LessonDomain.from_model(l) for l in Lesson.objects.filter(module_id=module_id)]

    @transaction.atomic
    def update_lesson(self, lesson_id: str, update_data: UpdateLessonDomain) -> Optional[LessonDomain]:
        try:
            lesson = Lesson.objects.get(id=lesson_id)
        except Lesson.DoesNotExist:
            return None
        update_data.validate()
        if update_data.title: lesson.title = update_data.title
        if update_data.position is not None: lesson.position = update_data.position
        if update_data.content_type: lesson.content_type = update_data.content_type
        lesson.save()
        return LessonDomain.from_model(lesson)

    @transaction.atomic
    def publish_lesson(self, lesson_id: str, publish_data: PublishLessonDomain) -> Optional[LessonDomain]:
        try:
            lesson = Lesson.objects.get(id=lesson_id)
        except Lesson.DoesNotExist:
            return None
        publish_data.validate()
        lesson.published = True  # PublishLessonDomain always publishes
        lesson.save()
        return LessonDomain.from_model(lesson)

    @transaction.atomic
    def reorder_lessons(self, module_id: str, reorder_data: ReorderLessonsDomain) -> None:
        reorder_data.validate()
        for lesson_id, pos in reorder_data.order_map.items():
            Lesson.objects.filter(id=lesson_id, module_id=module_id).update(position=pos)
