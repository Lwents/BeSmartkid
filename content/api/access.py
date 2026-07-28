from rest_framework.exceptions import PermissionDenied


TEACHER_ROLES = {"teacher", "instructor"}


def _role(user):
    return str(getattr(user, "role", "") or "").strip().lower()


def is_admin(user):
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and (
            getattr(user, "is_staff", False)
            or getattr(user, "is_superuser", False)
            or _role(user) == "admin"
        )
    )


def is_teacher(user):
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and _role(user) in TEACHER_ROLES
    )


def can_manage_course(user, course):
    if is_admin(user):
        return True
    return bool(is_teacher(user) and course and course.owner_id == user.id)


def can_view_course(user, course):
    if can_manage_course(user, course):
        return True
    return bool(course and course.published and not course.archived)


def require_content_author(user):
    if not (is_admin(user) or is_teacher(user)):
        raise PermissionDenied("Chỉ giáo viên hoặc quản trị viên được tạo nội dung.")


def require_course_manager(user, course):
    if not can_manage_course(user, course):
        raise PermissionDenied("Bạn không có quyền chỉnh sửa khóa học này.")


def require_course_viewer(user, course):
    if not can_view_course(user, course):
        raise PermissionDenied("Khóa học này chưa được công khai.")
