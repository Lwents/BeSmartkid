from django.conf import settings
from django.db.models import Count, Q, Prefetch
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
import json

from student_api.permissions import IsStudent
from content.models import Course, Enrollment, Lesson, LessonProgress, Module
from content.services.lesson_access_service import get_lesson_unlock_status
from ai_personalization.models import LearningPath


def build_media_url(request, file_field):
    """Return absolute URL for a FileField/ImageField if present."""
    if not file_field:
        return None

    url = getattr(file_field, 'url', None)
    if not url:
        return None

    if url.startswith('http://') or url.startswith('https://'):
        return url

    return request.build_absolute_uri(url)


def build_avatar_url(request, avatar_path: str | None):
    """Return absolute avatar URL for user profile strings/paths."""
    if not avatar_path:
        return None
    # Handle base64 data URLs - return as is (don't add /media/ prefix)
    if avatar_path.startswith('data:'):
        return avatar_path
    # Handle full URLs
    if avatar_path.startswith(("http://", "https://")):
        return avatar_path
    # Handle absolute paths
    if avatar_path.startswith('/'):
        return request.build_absolute_uri(avatar_path)
    # Handle relative paths
    media_url = getattr(settings, 'MEDIA_URL', '/media/')
    base = request.build_absolute_uri(media_url.rstrip('/') + '/')
    return f"{base}{avatar_path}"


class StudentMyCoursesView(APIView):
    """
    GET /api/student/courses/
    Returns enrolled courses for the student with progress
    """
    permission_classes = [IsAuthenticated, IsStudent]

    def get(self, request):
        """Get student's enrolled courses"""
        student = request.user
        
        # Get query parameters
        q = request.query_params.get('q', '').strip()
        grade = request.query_params.get('grade', '').strip()
        level = request.query_params.get('level', '').strip()  # 'main' or 'supp'
        
        # Get enrolled courses (only published courses)
        enrollments = Enrollment.objects.filter(
            student=student,
            course__published=True  # Only show published courses
        ).select_related('course', 'course__subject', 'course__owner')
        
        course_ids = [enrollment.course_id for enrollment in enrollments]
        lessons_count_map = {
            row['module__course_id']: row['count']
            for row in Lesson.objects.filter(
                module__course_id__in=course_ids,
                published=True
            ).values('module__course_id').annotate(count=Count('id'))
        }
        completed_count_map = {
            row['lesson__module__course_id']: row['count']
            for row in LessonProgress.objects.filter(
                lesson__module__course_id__in=course_ids,
                student=student,
                completed=True
            ).values('lesson__module__course_id').annotate(count=Count('id'))
        }
        enrollment_count_map = {
            row['course_id']: row['count']
            for row in Enrollment.objects.filter(
                course_id__in=course_ids
            ).values('course_id').annotate(count=Count('id'))
        }

        courses_data = []
        
        for enrollment in enrollments:
            course = enrollment.course
            
            grade_value = course.grade or ''
            grade_number = None
            try:
                grade_number = int(grade_value)
            except (ValueError, TypeError):
                grade_number = None
            
            if grade_number is not None:
                grade_label = 'Khối 1–2' if grade_number <= 2 else 'Khối 3–5'
            else:
                grade_label = 'Khối 1–2' if grade_value in ['1', '2', 'Khối 1–2', ''] else 'Khối 3–5'
            
            # Filter by search query
            if q and q.lower() not in course.title.lower():
                continue
            
            # Filter by grade
            if grade:
                if grade == 'Khối 1–2' and not (
                    (grade_number is not None and grade_number <= 2) or grade_value in ['1', '2', 'Khối 1–2']
                ):
                    continue
                if grade == 'Khối 3–5' and not (
                    (grade_number is not None and grade_number >= 3) or grade_value in ['3', '4', '5', 'Khối 3–5']
                ):
                    continue
            
            # Calculate progress
            total_lessons = lessons_count_map.get(course.id, 0)
            completed_lessons = completed_count_map.get(course.id, 0)
            
            progress = int((completed_lessons / total_lessons * 100)) if total_lessons > 0 else 0
            done = progress >= 100
            
            course_data = {
                'id': str(course.id),
                'title': course.title,
                'grade': grade_number if grade_number is not None else grade_value,
                'gradeLabel': grade_label,
                'gradeNumber': grade_number,
                'subject': course.subject.title if course.subject else '',
                'subjectSlug': course.subject.slug if course.subject else '',
                'teacherId': str(course.owner.id) if course.owner else '',
                'teacherName': (course.owner.profile.display_name if hasattr(course.owner, 'profile') and course.owner.profile.display_name else course.owner.username) if course.owner else '',
                'lessonsCount': total_lessons,
                'enrollments': enrollment_count_map.get(course.id, 0),
                'status': 'published' if course.published else 'draft',
                'createdAt': course.id.generation_time.isoformat() if hasattr(course.id, 'generation_time') else None,
                'updatedAt': None,
                'thumbnail': build_media_url(request, course.thumbnail),
                'isEnrolled': True,
                'progress': progress,
                'done': done,
            }
            
            courses_data.append(course_data)
        
        # Group by grade for frontend
        base_courses = [
            c for c in courses_data
            if (c.get('gradeNumber') is not None and c['gradeNumber'] <= 2)
            or c.get('grade') in ['1', '2', 'Khối 1–2']
        ]
        supp_courses = [
            c for c in courses_data
            if (c.get('gradeNumber') is not None and c['gradeNumber'] >= 3)
            or c.get('grade') in ['3', '4', '5', 'Khối 3–5']
        ]
        
        return Response({
            'base': base_courses,
            'supp': supp_courses,
            'all': courses_data,
        }, status=status.HTTP_200_OK)


class StudentCourseCatalogView(APIView):
    """
    GET /api/student/catalog/
    Returns all published courses (catalog view)
    """
    permission_classes = [IsAuthenticated, IsStudent]

    def get(self, request):
        """Get course catalog"""
        student = request.user
        
        # Get query parameters
        q = request.query_params.get('q', '').strip()
        grade = request.query_params.get('grade', '').strip()
        subject = request.query_params.get('subject', '').strip()
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('pageSize', 20))
        
        # Get all published courses
        courses = Course.objects.filter(
            published=True
        ).select_related('subject', 'owner')
        
        # Apply filters
        if q:
            courses = courses.filter(title__icontains=q)
        if grade:
            courses = courses.filter(grade=grade)
        if subject:
            courses = courses.filter(subject__slug=subject)
        
        # Pagination
        total = courses.count()
        start = (page - 1) * page_size
        end = start + page_size
        courses = list(courses[start:end])
        page_course_ids = [course.id for course in courses]
        lessons_count_map = {
            row['module__course_id']: row['count']
            for row in Lesson.objects.filter(
                module__course_id__in=page_course_ids,
                published=True
            ).values('module__course_id').annotate(count=Count('id'))
        }
        enrollment_count_map = {
            row['course_id']: row['count']
            for row in Enrollment.objects.filter(
                course_id__in=page_course_ids
            ).values('course_id').annotate(count=Count('id'))
        }
        
        # Check enrollment status for each course
        enrolled_course_ids = set(
            Enrollment.objects.filter(student=student)
            .values_list('course_id', flat=True)
        )
        
        courses_data = []
        for course in courses:
            # values_list() trả về UUID, vì vậy phải so sánh UUID với UUID.
            # So sánh chuỗi với UUID khiến mọi khóa học luôn hiện là chưa đăng ký.
            is_enrolled = course.id in enrolled_course_ids
            
            courses_data.append({
                'id': str(course.id),
                'title': course.title,
                'grade': course.grade or '',
                'subject': course.subject.title if course.subject else '',
                'teacherId': str(course.owner.id) if course.owner else '',
                'teacherName': (course.owner.profile.display_name if hasattr(course.owner, 'profile') and course.owner.profile.display_name else course.owner.username) if course.owner else '',
                'lessonsCount': lessons_count_map.get(course.id, 0),
                'enrollments': enrollment_count_map.get(course.id, 0),
                'status': 'published',
                'createdAt': course.id.generation_time.isoformat() if hasattr(course.id, 'generation_time') else None,
                'updatedAt': None,
                'thumbnail': course.thumbnail.url if course.thumbnail else None,
                'description': course.description or '',
                'introduction': course.introduction or '',
                'isEnrolled': is_enrolled,
            })
        
        return Response({
            'items': courses_data,
            'total': total,
        }, status=status.HTTP_200_OK)


class StudentCourseDetailView(APIView):
    """
    GET /api/student/courses/{id}/
    Returns course detail for student
    """
    permission_classes = [IsAuthenticated, IsStudent]

    def get(self, request, pk):
        """Get course detail"""
        student = request.user
        course = get_object_or_404(Course, pk=pk)
        
        # Students can only view published courses
        if not course.published:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("This course is not available yet.")
        
        # Check if student is enrolled
        is_enrolled = Enrollment.objects.filter(
            course=course,
            student=student
        ).exists()
        
        # Get modules and lessons
        modules = Module.objects.filter(course=course).prefetch_related(
            Prefetch(
                'lessons',
                queryset=Lesson.objects.filter(published=True).order_by('position')
            )
        ).order_by('position')
        
        lesson_ids = []
        for module in modules:
            lesson_ids.extend([lesson.id for lesson in module.lessons.all()])

        progress_map = {
            lp.lesson_id: lp
            for lp in LessonProgress.objects.filter(
                lesson_id__in=lesson_ids,
                student=student
            )
        }

        sections = []
        
        def _detect_content_type(lesson: Lesson):
            def _safe_parse(value):
                if isinstance(value, str):
                    trimmed = value.strip()
                    if trimmed and (
                        (trimmed.startswith('{') and trimmed.endswith('}')) or
                        (trimmed.startswith('[') and trimmed.endswith(']'))
                    ):
                        try:
                            return json.loads(trimmed)
                        except Exception:
                            return value
                return value

            def _extract_intro(raw):
                current = raw
                for _ in range(5):
                    if not current:
                        return None
                    if isinstance(current, str):
                        parsed = _safe_parse(current)
                        if parsed is current:
                            return None
                        current = parsed
                        continue
                    if isinstance(current, dict):
                        payload = _safe_parse(current.get('payload'))
                        if isinstance(payload, dict):
                            current = {**current, 'payload': payload}
                        content_type = current.get('contentType') or current.get('type')
                        if not content_type and isinstance(payload, dict):
                            content_type = payload.get('contentType') or payload.get('type')
                        if content_type or isinstance(payload, dict):
                            return {
                                'contentType': content_type,
                                'payload': payload if isinstance(payload, dict) else None,
                            }
                        if 'introduction' in current:
                            current = current['introduction']
                            continue
                        if isinstance(payload, dict):
                            current = payload
                            continue
                        return current
                return None

            def _kind_from_string(value):
                if not value:
                    return None
                lowered = str(value).lower()
                quiz_keys = ['quiz', 'exercise', 'question', 'exam', 'test', 'practice']
                video_keys = ['video', 'mp4', 'mov', 'avi', 'm4v', 'youtube', 'youtu', 'vimeo', 'mkv']
                pdf_keys = ['pdf']
                doc_keys = ['doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx', 'sheet', 'slides', 'presentation', 'document']
                image_keys = ['image', 'img', 'png', 'jpg', 'jpeg', 'gif', 'svg', 'bmp', 'webp', 'photo']
                text_keys = ['text', 'txt', 'markdown', 'note', 'article', 'md']
                if any(key in lowered for key in quiz_keys):
                    return 'quiz'
                if any(key in lowered for key in video_keys):
                    return 'video'
                if any(key in lowered for key in pdf_keys):
                    return 'pdf'
                if any(key in lowered for key in doc_keys):
                    return 'doc'
                if any(key in lowered for key in image_keys):
                    return 'image'
                if any(key in lowered for key in text_keys):
                    return 'text'
                return None

            def _kind_from_payload(payload):
                if not isinstance(payload, dict):
                    return None
                for key in ('contentType', 'type', 'mimeType', 'mime', 'fileType', 'format'):
                    match = _kind_from_string(payload.get(key))
                    if match:
                        return match
                file_name = payload.get('fileName') or payload.get('name')
                if isinstance(file_name, str):
                    match = _kind_from_string(file_name.split('.')[-1])
                    if match:
                        return match
                url = payload.get('url') or payload.get('fileData') or payload.get('embedUrl')
                if isinstance(url, str):
                    match = _kind_from_string(url)
                    if match:
                        return match
                if any(payload.get(key) for key in ('questions', 'quiz', 'items', 'choices', 'answers')):
                    return 'quiz'
                if any(payload.get(key) for key in ('text', 'content', 'html', 'markdown')):
                    return 'text'
                if any(payload.get(key) for key in ('image', 'imageUrl', 'image_url', 'images', 'picture')):
                    return 'image'
                return None

            # Ưu tiên kiểm tra content_type từ model trước
            content_type = lesson.content_type
            if content_type:
                if content_type in ('exercise', 'quiz'):
                    return 'quiz'
                if content_type == 'pdf':
                    return 'pdf'
                if content_type == 'text':
                    return 'text'
                if content_type == 'document':
                    return 'doc'
                if content_type == 'video':
                    return 'video'
            
            intro_meta = _extract_intro(getattr(lesson, "introduction", None))
            kind = None
            if intro_meta:
                kind = _kind_from_string(intro_meta.get('contentType'))
                if not kind:
                    kind = _kind_from_payload(intro_meta.get('payload'))
            if not kind and (lesson.video_url or lesson.video_file):
                kind = 'video'
            if not kind and hasattr(lesson, 'document_file') and lesson.document_file:
                kind = 'pdf'
            if not kind and hasattr(lesson, 'text_content') and lesson.text_content:
                kind = 'text'
            if not kind:
                kind = 'text'
            return kind
        previous_lessons_completed = True
        for module in modules:
            lessons = []
            for lesson in module.lessons.all():
                # Get progress for this lesson
                progress = progress_map.get(lesson.id)
                completed = progress.completed if progress else False
                
                lessons.append({
                    'id': str(lesson.id),
                    'title': lesson.title,
                    'type': _detect_content_type(lesson),
                    'content_type': lesson.content_type,
                    'durationMinutes': None,  # Could calculate from video if available
                    'isPreview': False,  # First lesson could be preview
                    'completed': completed,
                    'unlocked': previous_lessons_completed,
                    'videoWatched': progress.video_watched if progress else False,
                    'exerciseCompleted': progress.exercise_completed if progress else False,
                    'introduction': lesson.introduction or '',
                })
                previous_lessons_completed = previous_lessons_completed and completed
            
            sections.append({
                'id': str(module.id),
                'title': module.title,
                'order': module.position,
                'lessons': lessons,
            })
        
        # Calculate overall progress
        total_lessons = Lesson.objects.filter(
            module__course=course,
            published=True
        ).count()
        
        completed_lessons = LessonProgress.objects.filter(
            lesson__module__course=course,
            student=student,
            completed=True
        ).count()
        
        progress = int((completed_lessons / total_lessons * 100)) if total_lessons > 0 else 0

        # Build classmates list with progress
        classmates = Enrollment.objects.filter(course=course).select_related('student', 'student__profile')
        student_ids = [enrollment.student_id for enrollment in classmates]
        progress_map = {
            row['student_id']: row['completed']
            for row in LessonProgress.objects.filter(
                lesson__module__course=course,
                student_id__in=student_ids,
                completed=True
            ).values('student_id').annotate(completed=Count('id'))
        }

        students_data = []
        for enrollment in classmates:
            classmate = enrollment.student
            profile = getattr(classmate, 'profile', None)
            display_name = None
            avatar_path = None
            gender = None

            if profile:
                display_name = getattr(profile, 'display_name', None)
                avatar_path = getattr(profile, 'avatar_url', None)
                gender = getattr(profile, 'gender', None)

            if not display_name:
                # Custom user model (UserModel) does not implement get_full_name like Django's default User.
                # Guard against missing method to avoid AttributeError that was causing 500s for students.
                full_name = None
                get_full_name = getattr(classmate, 'get_full_name', None)
                if callable(get_full_name):
                    full_name = get_full_name()
                # Fall back to common attributes before defaulting to username/email
                if not full_name:
                    full_name = getattr(classmate, 'full_name', None)
                display_name = (
                    full_name
                    or getattr(classmate, 'username', None)
                    or getattr(classmate, 'email', None)
                    or 'Học viên'
                )

            if not avatar_path and hasattr(classmate, 'avatar'):
                avatar_path = getattr(classmate, 'avatar', None)

            # Get gender from profile or user model if not in profile
            if not gender:
                gender = getattr(classmate, 'gender', None)

            avatar_url = build_avatar_url(request, avatar_path)
            completed_for_student = progress_map.get(classmate.id, 0)
            student_progress = int((completed_for_student / total_lessons * 100)) if total_lessons > 0 else 0

            students_data.append({
                'id': str(classmate.id),
                'name': display_name,
                'avatar': avatar_url,
                'gender': gender,
                'progress': student_progress,
            })

        course_data = {
            'id': str(course.id),
            'title': course.title,
            'grade': course.grade or '',
            'subject': course.subject.title if course.subject else '',
            'teacherId': str(course.owner.id) if course.owner else '',
            'teacherName': (course.owner.profile.display_name if hasattr(course.owner, 'profile') and course.owner.profile.display_name else course.owner.username) if course.owner else '',
            'lessonsCount': total_lessons,
            'enrollments': course.enrollments.count(),
            'status': 'published' if course.published else 'draft',
            'createdAt': course.id.generation_time.isoformat() if hasattr(course.id, 'generation_time') else None,
            'updatedAt': None,
            'thumbnail': build_media_url(request, course.thumbnail),
            'description': course.description or '',
            'introduction': course.introduction or '',
            'video_url': course.video_url or '',
            'video_file': build_media_url(request, course.video_file),
            'sections': sections,
            'isEnrolled': is_enrolled,
            'progress': progress,
            'students': students_data,
        }
        
        return Response(course_data, status=status.HTTP_200_OK)


class StudentCoursePlayerView(APIView):
    """
    GET /api/student/courses/{id}/player/{lesson_id}/
    Returns lesson content for player
    """
    permission_classes = [IsAuthenticated, IsStudent]

    def get(self, request, pk, lesson_id=None):
        """Get lesson content for player"""
        student = request.user
        course = get_object_or_404(Course, pk=pk)
        
        # Check enrollment
        enrollment = Enrollment.objects.filter(
            course=course,
            student=student
        ).first()
        
        if not enrollment:
            return Response(
                {'detail': 'You are not enrolled in this course'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get lesson if specified
        if lesson_id:
            lesson = get_object_or_404(
                Lesson.objects.select_related('module', 'module__course'),
                pk=lesson_id,
                module__course=course,
                published=True,
            )
        else:
            lesson = Lesson.objects.select_related('module', 'module__course').filter(
                module__course=course,
                published=True
            ).order_by('module__position', 'position', 'id').first()
            
            if not lesson:
                return Response(
                    {'detail': 'No published lessons in this course'},
                    status=status.HTTP_404_NOT_FOUND
                )

        unlock_status = get_lesson_unlock_status(lesson, student)
        if not unlock_status.can_unlock:
            return Response({
                'detail': unlock_status.reason,
                'can_unlock': False,
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get or create progress
        progress, created = LessonProgress.objects.get_or_create(
            lesson=lesson,
            student=student
        )
        
        # Get lesson content
        lesson_data = {
            'id': str(lesson.id),
            'title': lesson.title,
            'content_type': lesson.content_type,
            'video_url': lesson.video_url or '',
            'video_file': build_media_url(request, lesson.video_file) if lesson.video_file else None,
            'document_file': build_media_url(request, lesson.document_file) if hasattr(lesson, 'document_file') and lesson.document_file else None,
            'text_content': lesson.text_content if hasattr(lesson, 'text_content') else None,
            'introduction': lesson.introduction or '',
            'requires_exercise_completion': lesson.requires_exercise_completion,
            'progress': {
                'completed': progress.completed,
                'video_watched': progress.video_watched,
                'exercise_completed': progress.exercise_completed,
                'exercise_score': progress.exercise_score,
                'started_at': progress.started_at.isoformat() if progress.started_at else None,
                'last_accessed_at': progress.last_accessed_at.isoformat() if progress.last_accessed_at else None,
            },
        }
        
        return Response(lesson_data, status=status.HTTP_200_OK)


class StudentLearningPathView(APIView):
    """
    GET /api/student/learning-path/
    Returns learning path for student
    """
    permission_classes = [IsAuthenticated, IsStudent]

    def get(self, request):
        """Get learning path"""
        student = request.user
        
        # Get enrolled courses grouped by grade
        enrollments = Enrollment.objects.filter(
            student=student
        ).select_related('course', 'course__subject')
        course_ids = [enrollment.course_id for enrollment in enrollments]
        lessons_count_map = {
            row['module__course_id']: row['count']
            for row in Lesson.objects.filter(
                module__course_id__in=course_ids,
                published=True
            ).values('module__course_id').annotate(count=Count('id'))
        }
        completed_count_map = {
            row['lesson__module__course_id']: row['count']
            for row in LessonProgress.objects.filter(
                lesson__module__course_id__in=course_ids,
                student=student,
                completed=True
            ).values('lesson__module__course_id').annotate(count=Count('id'))
        }
        
        # Group by grade
        path_data = {
            'grade_1_2': [],
            'grade_3_5': [],
        }
        
        for enrollment in enrollments:
            course = enrollment.course
            
            # Calculate progress
            total_lessons = lessons_count_map.get(course.id, 0)
            completed_lessons = completed_count_map.get(course.id, 0)
            
            progress = int((completed_lessons / total_lessons * 100)) if total_lessons > 0 else 0
            
            course_data = {
                'id': str(course.id),
                'title': course.title,
                'grade': course.grade or '',
                'subject': course.subject.title if course.subject else '',
                'progress': progress,
                'thumbnail': course.thumbnail.url if course.thumbnail else None,
            }
            
            if course.grade in ['1', '2', 'Khối 1–2']:
                path_data['grade_1_2'].append(course_data)
            else:
                path_data['grade_3_5'].append(course_data)
        
        return Response(path_data, status=status.HTTP_200_OK)


class StudentLearningPathManageView(APIView):
    """
    GET /api/student/learning-path/manage/?course_id=...
        - List all learning paths for student (if no course_id)
        - Or return detail for one course_id
    POST /api/student/learning-path/manage/
        - Create/regenerate a learning path for a course (overwrites existing)
        Payload: { "course_id": "<uuid|id>" }
    """
    permission_classes = [IsAuthenticated, IsStudent]

    def _build_steps(self, course):
        steps = []
        lessons = Lesson.objects.filter(
            module__course=course,
            published=True
        ).select_related('module').order_by('module__position', 'position', 'id')
        for idx, l in enumerate(lessons, start=1):
            steps.append({
                "lesson_id": str(l.id),
                "title": l.title,
                "module": l.module.title if l.module else '',
                "order": idx,
                "status": "pending",
            })
        return steps

    def _progress(self, student, course):
        total = Lesson.objects.filter(module__course=course, published=True).count()
        completed = LessonProgress.objects.filter(
            lesson__module__course=course,
            student=student,
            completed=True
        ).count()
        progress_pct = int((completed / total * 100)) if total > 0 else 0
        return total, completed, progress_pct

    def get(self, request):
        student = request.user
        course_id = request.query_params.get('course_id')

        qs = LearningPath.objects.filter(student=student).select_related('course')
        if course_id:
            qs = qs.filter(course_id=course_id)

        data = []
        for lp in qs:
            total, completed, progress_pct = self._progress(student, lp.course)
            next_steps = lp.path[:3] if isinstance(lp.path, list) else []
            data.append({
                "id": str(lp.id),
                "course_id": str(lp.course.id),
                "course_title": lp.course.title,
                "progress": progress_pct,
                "completed_steps": completed,
                "total_steps": total,
                "next_steps": next_steps,
                "generated_at": lp.generated_at.isoformat(),
                "metadata": lp.metadata or {},
            })

        if course_id:
            if not data:
                return Response({"detail": "Learning path not found"}, status=status.HTTP_404_NOT_FOUND)
            return Response(data[0], status=status.HTTP_200_OK)
        return Response(data, status=status.HTTP_200_OK)

    def post(self, request):
        student = request.user
        course_id = request.data.get('course_id')
        if not course_id:
            return Response({"detail": "course_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            course = Course.objects.get(id=course_id)
        except Course.DoesNotExist:
            return Response({"detail": "Course not found"}, status=status.HTTP_404_NOT_FOUND)

        # build path from published lessons
        steps = self._build_steps(course)
        lp, _ = LearningPath.objects.update_or_create(
            student=student,
            course=course,
            defaults={
                "path": steps,
                "metadata": {"generated_by": "student_api", "version": 1},
            },
        )

        total, completed, progress_pct = self._progress(student, course)
        return Response({
            "id": str(lp.id),
            "course_id": str(course.id),
            "course_title": course.title,
            "progress": progress_pct,
            "completed_steps": completed,
            "total_steps": total,
            "next_steps": lp.path[:3] if isinstance(lp.path, list) else [],
            "generated_at": lp.generated_at.isoformat(),
            "metadata": lp.metadata or {},
        }, status=status.HTTP_201_CREATED)
