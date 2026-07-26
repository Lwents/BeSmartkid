from django.db.models import Count, Q
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from teacher_api.permissions import IsTeacher
from content.models import Course, Enrollment, Lesson
from activities.models import Exercise, ExerciseAttempt
from school.models import ClassroomModel
from custom_account.models import UserModel


class TeacherDashboardView(APIView):
    """
    GET /api/teacher/dashboard/
    Returns dashboard stats for teacher:
    - Total courses
    - Total students (enrolled in teacher's courses)
    - Total assignments/lessons
    - My courses list (with enrollments count)
    """
    permission_classes = [IsAuthenticated, IsTeacher]

    def get(self, request):
        """Get teacher dashboard stats"""
        teacher = request.user
        
        # Get teacher's courses
        teacher_courses = Course.objects.filter(owner=teacher)
        
        # Total courses
        total_courses = teacher_courses.count()
        
        # Total students (unique students enrolled in teacher's courses)
        total_students = Enrollment.objects.filter(
            course__owner=teacher
        ).values('student').distinct().count()
        
        # Total lessons/assignments (count lessons in teacher's courses)
        total_lessons = Lesson.objects.filter(
            module__course__owner=teacher
        ).count()
        
        # Get teacher's courses with enrollment counts (for dashboard display)
        courses_with_stats = teacher_courses.annotate(
            enrollments_count=Count('enrollments', distinct=True),
            lessons_count=Count('modules__lessons', distinct=True)
        ).order_by('-id')[:8]  # Limit to 8 for dashboard, order by id (newest first)
        
        my_courses = [
            {
                'id': str(course.id),
                'title': course.title,
                'enrolled': course.enrollments_count,
                'lessons': course.lessons_count,
                'status': 'published' if course.published else 'draft',
                'updatedAt': None,  # Course model doesn't have updated_at field
                'createdAt': None,  # Course model doesn't have created_at field
            }
            for course in courses_with_stats
        ]
        
        # Bài kiểm tra của giáo viên: đề độc lập gắn khóa của mình, hoặc đề trong
        # bài học của mình. Trước đây dashboard không trả số này nên app luôn hiện 0.
        course_ids = list(teacher_courses.values_list('id', flat=True))
        exams_query = Exercise.objects.filter(
            Q(lesson__module__course__owner=teacher)
            | Q(settings__course_id__in=course_ids)
        ).distinct()
        total_exams = exams_query.count()

        # Lượt học sinh đã nộp bài trên các đề đó.
        total_attempts = ExerciseAttempt.objects.filter(
            exercise__in=exams_query, finished_at__isnull=False
        ).count()

        return Response({
            'stats': {
                'courses': total_courses,
                'students': total_students,
                'assignments': total_lessons,
                'exams': total_exams,
                'attempts': total_attempts,
            },
            'myCourses': my_courses
        }, status=status.HTTP_200_OK)

