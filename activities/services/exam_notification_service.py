from activities.models import Notification
from content.models import Course, Enrollment


def notify_enrolled_students_about_exam(exercise):
    """Notify each enrolled student once when an exam becomes available."""
    if exercise is None or not exercise.published:
        return 0
    course = _exercise_course(exercise)
    if course is None:
        return 0

    student_ids = set(Enrollment.objects.filter(course=course).values_list(
        "student_id", flat=True
    ))
    if not student_ids:
        return 0
    exercise_id = str(exercise.id)
    already_notified = set(Notification.objects.filter(
        user_id__in=student_ids,
        category="exam",
        metadata__exercise_id=exercise_id,
    ).values_list("user_id", flat=True))

    notifications = [
        Notification(
            user_id=student_id,
            title="Có bài kiểm tra mới",
            message=f"Thầy cô vừa giao bài “{exercise.title}”. Em vào làm bài nhé!",
            type="info",
            category="exam",
            metadata={
                "exercise_id": exercise_id,
                "exam_id": exercise_id,
                "exam_title": exercise.title,
                "course_id": str(course.id),
                "course_title": course.title,
            },
        )
        for student_id in student_ids
        if student_id not in already_notified
    ]
    Notification.objects.bulk_create(notifications)
    return len(notifications)


def _exercise_course(exercise):
    try:
        course_id = exercise.settings.course_id
        if course_id:
            return Course.objects.filter(id=course_id).first()
    except Exception:
        pass
    try:
        return exercise.lesson.module.course if exercise.lesson_id else None
    except Exception:
        return None
