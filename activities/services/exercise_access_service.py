from content.models import Course, Enrollment
from content.services.lesson_access_service import get_lesson_unlock_status


TEACHER_ROLES = {"teacher", "instructor"}


def role_of(user):
    return str(getattr(user, "role", "") or "").strip().lower()


def is_admin(user):
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and (getattr(user, "is_staff", False) or role_of(user) == "admin")
    )


def is_teacher(user):
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and role_of(user) in TEACHER_ROLES
    )


def is_student(user):
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and role_of(user) == "student"
    )


def exercise_course(exercise):
    """Resolve the course for standalone exams and lesson exercises."""
    try:
        course_id = exercise.settings.course_id
    except Exception:
        course_id = None
    if course_id:
        return Course.objects.filter(id=course_id).first()

    try:
        if exercise.lesson_id:
            return exercise.lesson.module.course
    except Exception:
        return None
    return None


def course_from_exercise_payload(data):
    settings = data.get("settings") or {}
    course_id = settings.get("course_id") if hasattr(settings, "get") else None
    if course_id:
        return Course.objects.filter(id=course_id).first()

    lesson_id = data.get("lesson") if hasattr(data, "get") else None
    if lesson_id:
        return Course.objects.filter(modules__lessons__id=lesson_id).first()
    return None


def can_manage_course(user, course):
    if is_admin(user):
        return True
    return bool(is_teacher(user) and course and course.owner_id == user.id)


def can_manage_exercise(user, exercise):
    return can_manage_course(user, exercise_course(exercise))


def student_can_access_exercise(user, exercise, *, require_unlocked=True):
    if exercise is None or not is_student(user) or not exercise.published:
        return False

    course = exercise_course(exercise)
    if course is None or not course.published:
        return False
    if not Enrollment.objects.filter(course=course, student=user).exists():
        return False

    try:
        lesson = exercise.lesson if exercise.lesson_id else None
    except Exception:
        lesson = None
    if lesson is not None:
        if not lesson.published:
            return False
        if require_unlocked and not get_lesson_unlock_status(lesson, user).can_unlock:
            return False
    return True


def can_view_exercise(user, exercise):
    if can_manage_exercise(user, exercise):
        return True
    return student_can_access_exercise(user, exercise)
