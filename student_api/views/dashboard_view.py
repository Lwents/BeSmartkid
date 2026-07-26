import re
from django.db.models import Count, Q, F, Case, When, IntegerField
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from student_api.permissions import IsStudent
from content.models import Course, Enrollment, Lesson, LessonProgress, Module
from activities.models import Exercise


class StudentDashboardView(APIView):
    """
    GET /api/student/dashboard/
    Returns dashboard data for student:
    - Resume course (course with progress > 0 and < 100)
    - Featured courses (enrolled courses with progress)
    - Preview exams (published exercises)
    """
    permission_classes = [IsAuthenticated, IsStudent]

    def get(self, request):
        """Get student dashboard data"""
        student = request.user
        
        # Get enrolled courses with progress calculation
        enrollments = Enrollment.objects.filter(student=student).select_related('course')
        
        courses_data = []
        resume_course = None
        
        for enrollment in enrollments:
            course = enrollment.course
            
            # Calculate progress: count completed lessons / total lessons
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
            done = progress >= 100
            
            course_data = {
                'id': str(course.id),
                'title': course.title,
                'grade': course.grade or '',
                'subject': course.subject.title if course.subject else '',
                'teacherId': str(course.owner.id) if course.owner else '',
                'teacherName': course.owner.get_full_name() or course.owner.username if course.owner else '',
                'lessonsCount': total_lessons,
                'enrollments': course.enrollments.count(),
                'status': 'published' if course.published else 'draft',
                'createdAt': course.id.generation_time.isoformat() if hasattr(course.id, 'generation_time') else None,
                'updatedAt': None,
                'thumbnail': course.thumbnail.url if course.thumbnail else None,
                'progress': progress,
                'done': done,
            }
            
            courses_data.append(course_data)
            
            # Find resume course (first course with progress > 0 and < 100)
            if resume_course is None and progress > 0 and progress < 100:
                resume_course = course_data
        
        # If no resume course, use first course
        if resume_course is None and courses_data:
            resume_course = courses_data[0]
        
        # Get featured courses (limit to 6, sorted by last accessed)
        featured = sorted(
            courses_data,
            key=lambda x: x.get('updatedAt') or '',
            reverse=True
        )[:6]
        
        # Preview exams: phải cùng bộ lọc với /student/exams/ để trang chủ không
        # đếm đề nháp hoặc đề của khóa học sinh chưa tham gia.
        enrolled_course_ids = {str(item['id']) for item in courses_data}
        enrolled_grades = {
            re.sub(r'\D', '', str(item.get('grade') or '')) or None
            for item in courses_data
        }
        enrolled_grades.discard(None)

        exercises = (
            Exercise.objects
            .filter(published=True, lesson__isnull=True)
            .select_related('settings')
            .order_by('-id')
        )

        preview_exams = []
        for exercise in exercises:
            settings_obj = getattr(exercise, 'settings', None)
            course_id = str(getattr(settings_obj, 'course_id', '') or '')
            if not course_id or course_id not in enrolled_course_ids:
                continue

            duration_sec = 1800  # Default 30 minutes
            pass_score = 12  # Default
            try:
                if settings_obj:
                    duration_sec = settings_obj.time_limit_seconds or duration_sec
                    pass_score = settings_obj.pass_score or pass_score
            except Exception:
                pass

            course_grade = next(
                (item.get('grade') for item in courses_data if str(item['id']) == course_id),
                '',
            )
            digits = re.sub(r'\D', '', str(course_grade or ''))
            if digits and int(digits) <= 2:
                grade = 'Khối 1–2'
            elif digits:
                grade = 'Khối 3–5'
            else:
                grade = course_grade or ''

            preview_exams.append({
                'id': str(exercise.id),
                'title': exercise.title,
                'grade': grade,
                'duration': duration_sec,
                'pass': pass_score,
            })
            if len(preview_exams) >= 5:
                break
        
        return Response({
            'resumeCourse': resume_course,
            'featured': featured,
            'previewExams': preview_exams,
        }, status=status.HTTP_200_OK)

