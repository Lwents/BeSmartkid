from dataclasses import dataclass

from django.db.models import Q

from content.models import Lesson, LessonProgress


@dataclass(frozen=True)
class LessonUnlockStatus:
    can_unlock: bool
    reason: str | None = None
    blocking_lesson: Lesson | None = None


def get_lesson_unlock_status(lesson: Lesson, student) -> LessonUnlockStatus:
    """Require every published lesson before ``lesson`` to be completed."""
    prerequisite_lessons = Lesson.objects.filter(
        module__course_id=lesson.module.course_id,
        published=True,
    ).filter(
        Q(module__position__lt=lesson.module.position)
        | Q(module_id=lesson.module_id, position__lt=lesson.position)
    )

    completed_lesson_ids = LessonProgress.objects.filter(
        lesson__in=prerequisite_lessons,
        student=student,
        completed=True,
    ).values_list("lesson_id", flat=True)

    blocking_lesson = (
        prerequisite_lessons.exclude(id__in=completed_lesson_ids)
        .select_related("module")
        .order_by("module__position", "position", "id")
        .first()
    )
    if blocking_lesson is None:
        return LessonUnlockStatus(can_unlock=True)

    if blocking_lesson.module_id != lesson.module_id:
        reason = (
            f"Bạn cần hoàn thành tất cả bài học trong "
            f"{blocking_lesson.module.title} trước khi xem {lesson.module.title}"
        )
    else:
        reason = f"Bạn cần hoàn thành bài học trước: {blocking_lesson.title}"

    return LessonUnlockStatus(
        can_unlock=False,
        reason=reason,
        blocking_lesson=blocking_lesson,
    )
