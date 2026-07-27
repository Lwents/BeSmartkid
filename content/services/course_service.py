from typing import List, Optional
from django.db import transaction
from django.contrib.auth import get_user_model

from content.models import Course, Subject, Enrollment
from content.domains.course_domain import (
    CourseDomain, CreateCourseDomain, UpdateCourseDomain,
    CoursePublishDomain, CourseAssignOwnerDomain
)

User = get_user_model()


class CourseService:
    """Application service for managing courses."""

    @transaction.atomic
    def create_course(self, input_data: CreateCourseDomain) -> CourseDomain:
        input_data.validate()
        
        # Kiểm tra tên khóa học đã tồn tại chưa
        if Course.objects.filter(title__iexact=input_data.title.strip()).exists():
            from content.services.exceptions import DomainValidationError
            raise DomainValidationError(f"Tên khóa học '{input_data.title}' đã tồn tại. Vui lòng chọn tên khác.")
        
        subject = None
        if input_data.subject_id:
            subject = Subject.objects.filter(id=input_data.subject_id).first()
        owner = None
        if input_data.owner_id:
            owner = User.objects.filter(id=input_data.owner_id).first()
        course = Course.objects.create(
            subject=subject,
            title=input_data.title,
            description=input_data.description,
            introduction=input_data.introduction,
            grade=input_data.grade,
            owner=owner,
            published=False,
            video_url=input_data.video_url
        )
        return CourseDomain.from_model(course)

    def get_course(self, course_id: str) -> Optional[CourseDomain]:
        try:
            # Prefetch để load đầy đủ modules, lessons và versions
            course = Course.objects.prefetch_related(
                'modules',
                'modules__lessons',
                'modules__lessons__versions'
            ).get(id=course_id)
            return CourseDomain.from_model(course)
        except Course.DoesNotExist:
            return None

    def list_courses(self, subject_id: Optional[str] = None, published: Optional[bool] = None) -> List[CourseDomain]:
        qs = Course.objects.all()
        if subject_id:
            qs = qs.filter(subject_id=subject_id)
        if published is not None:
            qs = qs.filter(published=published)
        return [CourseDomain.from_model(c) for c in qs]

    @transaction.atomic
    def update_course(self, course_id: str, update_data: UpdateCourseDomain) -> Optional[CourseDomain]:
        try:
            course = Course.objects.get(id=course_id)
        except Course.DoesNotExist:
            return None
        update_data.validate()
        if update_data.title is not None: course.title = update_data.title
        if update_data.description is not None: course.description = update_data.description
        if update_data.grade is not None: course.grade = update_data.grade
        if update_data.introduction is not None: course.introduction = update_data.introduction
        # Handle published: if set to False, just update. If set to True, we should use publish_course instead
        # But for simplicity, allow direct update here. The publish endpoint will do validation.
        if update_data.published is not None:
            course.published = update_data.published
        course.save()
        return CourseDomain.from_model(course)

    @transaction.atomic
    def publish_course(self, course_id: str, publish_data: CoursePublishDomain) -> Optional[CourseDomain]:
        try:
            # Load course with all related data for validation
            from content.models import Module, Lesson, LessonVersion
            course = Course.objects.prefetch_related(
                'modules',
                'modules__lessons',
                'modules__lessons__versions'
            ).get(id=course_id)
        except Course.DoesNotExist:
            return None
        publish_data.validate()
        # Get domain to check publish rules (load modules and lessons)
        course_domain = CourseDomain.from_model(course)
        # Load modules with lessons and versions into domain for validation
        from content.domains.module_domain import ModuleDomain
        from content.domains.lesson_domain import LessonDomain
        course_domain.modules = []
        for module_model in course.modules.all():
            module_domain = ModuleDomain.from_model(module_model)
            # Load lessons with versions
            module_domain.lessons = []
            for lesson_model in module_model.lessons.all():
                # Ensure legacy lessons have at least one published version
                if not lesson_model.versions.exists():
                    LessonVersion.objects.create(
                        lesson=lesson_model,
                        version=1,
                        status='published',
                        content={"structure": "lesson", "content_blocks": []},
                    )
                lesson_domain = LessonDomain.from_model(lesson_model)
                # Load versions
                from content.domains.lesson_version_domain import LessonVersionDomain
                lesson_domain.versions = [
                    LessonVersionDomain.from_model(v) 
                    for v in lesson_model.versions.all()
                ]
                module_domain.lessons.append(lesson_domain)
            course_domain.modules.append(module_domain)
        # Check if can publish
        can_publish, reason = course_domain.can_publish(require_all_lessons_published=publish_data.require_all_lessons_published)
        if not can_publish:
            raise ValueError(reason)
        course.published = True
        course.save()
        return CourseDomain.from_model(course)

    @transaction.atomic
    def assign_owner(self, course_id: str, assign_data: CourseAssignOwnerDomain) -> Optional[CourseDomain]:
        try:
            course = Course.objects.get(id=course_id)
        except Course.DoesNotExist:
            return None
        owner = User.objects.filter(id=assign_data.owner_id).first()
        if not owner:
            raise ValueError("Owner does not exist.")
        course.owner = owner
        course.save()
        return CourseDomain.from_model(course)
    
    def enroll_user(self, course_id: str, user_id: int) -> bool:
        """Enroll a user to a course."""
        try:
            course = Course.objects.get(id=course_id)
            user = User.objects.get(id=user_id)
            # Create enrollment if it doesn't exist
            enrollment, created = Enrollment.objects.get_or_create(
                course=course,
                student=user
            )
            return True
        except (Course.DoesNotExist, User.DoesNotExist) as e:
            raise ValueError(f"Course or User not found: {e}")
    
    def unenroll_user(self, course_id: str, user_id: int) -> bool:
        """Unenroll a user from a course."""
        try:
            course = Course.objects.get(id=course_id)
            user = User.objects.get(id=user_id)
            Enrollment.objects.filter(course=course, student=user).delete()
            return True
        except (Course.DoesNotExist, User.DoesNotExist) as e:
            raise ValueError(f"Course or User not found: {e}")
