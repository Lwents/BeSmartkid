from django.db.models import Count, Q
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from teacher_api.permissions import IsTeacher
from content.models import Course, Enrollment, Lesson, LessonProgress
from activities.models import Exercise, ExerciseAttempt
from custom_account.models import UserModel


def _percentage(part, total):
    if total <= 0:
        return 0
    return min(100, max(0, round(part * 100 / total)))


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
        enrollments_query = Enrollment.objects.filter(
            course__owner=teacher
        )
        student_ids = enrollments_query.values_list('student_id', flat=True).distinct()
        total_students = student_ids.count()
        
        # Total lessons/assignments (count lessons in teacher's courses)
        total_lessons = Lesson.objects.filter(
            module__course__owner=teacher
        ).count()
        published_lessons = Lesson.objects.filter(
            module__course__owner=teacher,
            published=True,
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
        published_exams = exams_query.filter(published=True).count()

        attempts_query = ExerciseAttempt.objects.filter(exercise__in=exams_query)
        all_attempts = attempts_query.count()
        total_attempts = attempts_query.filter(finished_at__isnull=False).count()

        active_students = UserModel.objects.filter(id__in=student_ids).filter(
            Q(lesson_progress__lesson__module__course__owner=teacher)
            | Q(exercise_attempts__exercise__in=exams_query)
        ).distinct().count()

        lesson_progress_query = LessonProgress.objects.filter(
            lesson__module__course__owner=teacher
        )
        started_lessons = lesson_progress_query.count()
        completed_lessons = lesson_progress_query.filter(completed=True).count()

        return Response({
            'stats': {
                'courses': total_courses,
                'students': total_students,
                'assignments': total_lessons,
                'exams': total_exams,
                'attempts': total_attempts,
            },
            'rates': {
                'coursePublished': _percentage(
                    teacher_courses.filter(published=True).count(), total_courses
                ),
                'studentActive': _percentage(active_students, total_students),
                'lessonPublished': _percentage(published_lessons, total_lessons),
                'examPublished': _percentage(published_exams, total_exams),
                'attemptSubmitted': _percentage(total_attempts, all_attempts),
                'completion': _percentage(completed_lessons, started_lessons),
            },
            'myCourses': my_courses
        }, status=status.HTTP_200_OK)
