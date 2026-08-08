from django.db import transaction
from django.core.mail import send_mail
from django.conf import settings
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import serializers
import logging

from teacher_api.permissions import IsTeacher
from activities.models import TeacherFeedback, Notification
from content.models import Course, Enrollment
from custom_account.models import UserModel

logger = logging.getLogger(__name__)


class TeacherFeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeacherFeedback
        fields = ['id', 'teacher', 'student', 'course', 'message', 'created_at', 'updated_at', 'is_read']
        read_only_fields = ['id', 'teacher', 'created_at', 'updated_at']


class TeacherFeedbackView(APIView):
    """
    POST /api/teacher/students/feedback/
    Send feedback to a student
    """
    permission_classes = [IsAuthenticated, IsTeacher]

    def get(self, request):
        return TeacherFeedbackListView().get(request)

    def post(self, request):
        try:
            teacher = request.user
            student_id = request.data.get('studentId')
            course_id = request.data.get('courseId')
            message = request.data.get('message', '').strip()

            if not student_id:
                return Response({'error': 'studentId is required'}, status=status.HTTP_400_BAD_REQUEST)

            if not message:
                return Response({'error': 'message is required'}, status=status.HTTP_400_BAD_REQUEST)

            try:
                student = UserModel.objects.get(id=student_id, role='student')
            except UserModel.DoesNotExist:
                return Response({'error': 'Student not found'}, status=status.HTTP_404_NOT_FOUND)

            # Verify teacher has access to this student (student enrolled in teacher's course)
            if course_id:
                try:
                    course = Course.objects.get(id=course_id, owner=teacher)
                    enrollment = Enrollment.objects.filter(course=course, student=student).first()
                    if not enrollment:
                        return Response({'error': 'Student is not enrolled in this course'}, status=status.HTTP_403_FORBIDDEN)
                except Course.DoesNotExist:
                    return Response({'error': 'Course not found'}, status=status.HTTP_404_NOT_FOUND)
            else:
                # If no course specified, check if student is enrolled in any of teacher's courses
                has_access = Enrollment.objects.filter(
                    course__owner=teacher,
                    student=student
                ).exists()
                if not has_access:
                    return Response({'error': 'Student is not enrolled in any of your courses'}, status=status.HTTP_403_FORBIDDEN)

            course_obj = None
            if course_id:
                try:
                    course_obj = Course.objects.get(id=course_id)
                except Course.DoesNotExist:
                    pass

            with transaction.atomic():
                # Create feedback
                feedback = TeacherFeedback.objects.create(
                    teacher=teacher,
                    student=student,
                    course=course_obj,
                    message=message
                )

                # Create notification for student
                try:
                    teacher_name = getattr(teacher, 'name', None) or getattr(teacher, 'username', 'Giáo viên')
                    # Try to get display_name from teacher profile
                    if hasattr(teacher, 'profile') and teacher.profile:
                        teacher_display_name = getattr(teacher.profile, 'display_name', None)
                        if teacher_display_name:
                            teacher_name = teacher_display_name
                    
                    notification_message = f'{teacher_name} đã gửi phản hồi cho bạn: {message[:100]}'
                    if len(message) > 100:
                        notification_message += '...'
                    
                    Notification.objects.create(
                        user=student,
                        title='Phản hồi từ giáo viên',
                        message=notification_message,
                        type='info',
                        category='feedback',
                        metadata={'feedback_id': str(feedback.id), 'teacher_id': str(teacher.id)}
                    )
                    logger.info(f"Notification created for student {student.id} from teacher {teacher.id}")
                except Exception as notif_error:
                    # Log error but don't fail the feedback creation
                    logger.error(f"Error creating notification: {notif_error}", exc_info=True)
                
                # Send email to student
                try:
                    student_email = getattr(student, 'email', None)
                    student_name = getattr(student, 'username', 'Học sinh')
                    # Try to get display_name from student profile
                    if hasattr(student, 'profile') and student.profile:
                        student_display_name = getattr(student.profile, 'display_name', None)
                        if student_display_name:
                            student_name = student_display_name
                    
                    if student_email:
                        email_subject = f'Phản hồi từ giáo viên {teacher_name}'
                        email_message = f'''Xin chào {student_name},

Giáo viên {teacher_name} đã gửi phản hồi cho bạn:

{message}

Bạn có thể xem chi tiết phản hồi trong hệ thống SmartKid.

Trân trọng,
Đội ngũ SmartKid
'''
                        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@smartkid.vn')
                        send_mail(
                            subject=email_subject,
                            message=email_message,
                            from_email=from_email,
                            recipient_list=[student_email],
                            fail_silently=True,  # Don't fail feedback creation if email fails
                        )
                        logger.info(f"Email sent to student {student.id} ({student_email})")
                except Exception as email_error:
                    # Log error but don't fail the feedback creation
                    logger.error(f"Error sending email: {email_error}", exc_info=True)

            serializer = TeacherFeedbackSerializer(feedback)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Error in TeacherFeedbackView: {e}", exc_info=True)
            return Response({'error': f'Internal Server Error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class TeacherFeedbackListView(APIView):
    """
    GET /api/teacher/students/feedback/
    List all feedbacks sent by teacher
    """
    permission_classes = [IsAuthenticated, IsTeacher]

    def get(self, request):
        try:
            teacher = request.user
            student_id = request.query_params.get('studentId')
            course_id = request.query_params.get('courseId')

            queryset = TeacherFeedback.objects.filter(teacher=teacher).select_related('student', 'course', 'student__profile')

            if student_id:
                queryset = queryset.filter(student_id=student_id)
            if course_id:
                queryset = queryset.filter(course_id=course_id)

            feedbacks = queryset.order_by('-created_at')[:50]

            result = []
            for fb in feedbacks:
                student_name = getattr(fb.student, 'username', 'N/A')
                if hasattr(fb.student, 'profile') and fb.student.profile:
                    student_name = getattr(fb.student.profile, 'display_name', student_name)

                result.append({
                    'id': str(fb.id),
                    'studentId': str(fb.student.id),
                    'studentName': student_name,
                    'courseId': str(fb.course.id) if fb.course else None,
                    'courseTitle': fb.course.title if fb.course else None,
                    'message': fb.message,
                    'createdAt': fb.created_at.isoformat(),
                    'isRead': fb.is_read
                })

            return Response({'items': result}, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error in TeacherFeedbackListView: {e}", exc_info=True)
            return Response({'error': f'Internal Server Error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
