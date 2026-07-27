from django.db.models import Avg, Q
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
import logging

from teacher_api.permissions import IsTeacher
from content.models import Course, Enrollment, LessonProgress
from activities.models import ExerciseAttempt

logger = logging.getLogger(__name__)


class TeacherStudentsView(APIView):
    """
    GET /api/teacher/students/
    Returns list of students enrolled in teacher's courses with:
    - Student info
    - Courses they're enrolled in
    - Progress for each course
    """
    permission_classes = [IsAuthenticated, IsTeacher]

    def get(self, request):
        """Get students enrolled in teacher's courses"""
        try:
            teacher = request.user
            
            # Get all enrollments for teacher's courses
            enrollments = Enrollment.objects.filter(
                course__owner=teacher
            ).select_related('student', 'course', 'student__profile').prefetch_related(
                'course__modules',
                'course__modules__lessons'
            ).order_by('-enrolled_at')
            teacher_course_ids = Course.objects.filter(owner=teacher).values_list('id', flat=True)
            
            # Group by student
            students_dict = {}
            for enrollment in enrollments:
                try:
                    student = enrollment.student
                    course = enrollment.course
                    
                    student_id = str(student.id)
                    course_id = str(course.id)
                    
                    if student_id not in students_dict:
                        # Safely get student attributes
                        # Try to get name from profile first, then fallback to username
                        student_name = None
                        student_avatar = None
                        try:
                            # Profile is already prefetched via select_related
                            if hasattr(student, 'profile') and student.profile:
                                profile = student.profile
                                student_name = getattr(profile, 'display_name', None)
                                student_avatar = getattr(profile, 'avatar_url', None)
                                
                                # Build full avatar URL if it's a relative path
                                if student_avatar and not student_avatar.startswith('http://') and not student_avatar.startswith('https://') and not student_avatar.startswith('data:'):
                                    from django.conf import settings
                                    # Get request to build absolute URL
                                    request = self.request
                                    if request:
                                        # Use request.build_absolute_uri for full URL
                                        if student_avatar.startswith('/'):
                                            student_avatar = request.build_absolute_uri(student_avatar)
                                        else:
                                            media_url = getattr(settings, 'MEDIA_URL', '/media/')
                                            student_avatar = request.build_absolute_uri(f"{media_url.rstrip('/')}/{student_avatar}")
                                    else:
                                        # Fallback: use MEDIA_URL if no request available
                                        media_url = getattr(settings, 'MEDIA_URL', '/media/')
                                        if not student_avatar.startswith('/'):
                                            student_avatar = f"{media_url}{student_avatar}"
                                        else:
                                            student_avatar = f"{media_url.rstrip('/')}{student_avatar}"
                        except Exception as e:
                            logger.debug(f"Error getting profile for student {student_id}: {e}")
                        
                        # Fallback to username if no display_name
                        if not student_name:
                            student_name = getattr(student, 'username', 'N/A')
                        
                        student_username = getattr(student, 'username', 'N/A')
                        student_email = getattr(student, 'email', '')
                        
                        attempts = ExerciseAttempt.objects.filter(
                            student=student,
                            score__isnull=False,
                        ).filter(
                            Q(exercise__lesson__module__course__owner=teacher)
                            | Q(exercise__settings__course_id__in=teacher_course_ids)
                        )
                        avg_score = attempts.aggregate(value=Avg('score'))['value'] or 0.0
                        
                        # Get last activity time
                        last_active = 'Chưa có'
                        if student.last_login:
                            from django.utils import timezone
                            delta = timezone.now() - student.last_login
                            if delta.days > 0:
                                last_active = f'{delta.days} ngày trước'
                            elif delta.seconds // 3600 > 0:
                                last_active = f'{delta.seconds // 3600} giờ trước'
                            else:
                                last_active = f'{delta.seconds // 60} phút trước'
                        
                        students_dict[student_id] = {
                            'id': student_id,
                            'name': student_name,
                            'username': student_username,
                            'email': student_email,
                            'avatar': student_avatar,
                            'avgScore': round(avg_score, 1),
                            'lastActive': last_active,
                            'courses': []
                        }
                    
                    # Calculate progress for this course
                    total_lessons = 0
                    completed_lessons = 0
                    
                    # Count total lessons
                    try:
                        for module in course.modules.all():
                            lessons = module.lessons.all()
                            total_lessons += lessons.count()
                            # Count completed lessons
                            for lesson in lessons:
                                progress = LessonProgress.objects.filter(
                                    student=student,
                                    lesson=lesson,
                                    completed=True
                                ).first()
                                if progress:
                                    completed_lessons += 1
                    except Exception as e:
                        logger.warning(f"Error calculating progress for course {course_id}: {e}")
                        # Continue with 0 progress if there's an error
                    
                    progress_pct = round((completed_lessons / total_lessons * 100) if total_lessons > 0 else 0)
                    
                    students_dict[student_id]['courses'].append({
                        'id': course_id,
                        'title': getattr(course, 'title', 'Khóa học'),
                        'grade': getattr(course, 'grade', ''),
                        'enrolledAt': enrollment.enrolled_at.isoformat() if enrollment.enrolled_at else '',
                        'progress': progress_pct,
                        'completedLessons': completed_lessons,
                        'totalLessons': total_lessons,
                        'status': 'completed' if progress_pct >= 100 else 'in_progress'
                    })
                except Exception as e:
                    logger.error(f"Error processing enrollment {enrollment.id}: {e}")
                    continue  # Skip this enrollment if there's an error
            
            # Convert to list
            students_list = list(students_dict.values())
            
            # Apply filters
            q = request.query_params.get('q', '').strip()
            course_id = request.query_params.get('courseId', '').strip()
            
            if q:
                students_list = [
                    s for s in students_list
                    if q.lower() in (s.get('name', '') or '').lower() or
                       q.lower() in (s.get('username', '') or '').lower() or
                       q.lower() in (s.get('email', '') or '').lower()
                ]
            
            if course_id:
                students_list = [
                    s for s in students_list
                    if any(c.get('id') == course_id for c in s.get('courses', []))
                ]
            
            # Pagination
            try:
                page = int(request.query_params.get('page', 1))
                page_size = int(request.query_params.get('pageSize', 20))
            except (ValueError, TypeError):
                page = 1
                page_size = 20
            
            start = (page - 1) * page_size
            end = start + page_size
            
            total = len(students_list)
            items = students_list[start:end]
            
            return Response({
                'items': items,
                'total': total,
                'page': page,
                'pageSize': page_size
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error in TeacherStudentsView: {e}", exc_info=True)
            return Response({
                'detail': f'Internal Server Error: {str(e)}',
                'items': [],
                'total': 0,
                'page': 1,
                'pageSize': 20
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
