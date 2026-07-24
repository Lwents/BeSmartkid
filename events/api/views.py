"""
Event API: giáo viên tạo/cập nhật sự kiện, học sinh xem sự kiện sắp tới.
Liên kết FE: eventService.* (FE gọi /events/teacher/, /events/upcoming/).
"""
import datetime
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.utils import timezone
from django.db.models import Q
from django.utils.dateparse import parse_datetime, parse_date

from events.models import PlatformEvent
from activities.models import Notification
from content.models import Course, Enrollment


class DateParsingMixin:
    """Shared helpers for parsing incoming date/datetime values."""
    def _parse_datetime(self, value):
        """Parse incoming date/datetime string to aware datetime."""
        if isinstance(value, datetime.datetime):
            dt = value
        elif isinstance(value, datetime.date):
            dt = datetime.datetime.combine(value, datetime.time.min)
        elif isinstance(value, str):
            dt = parse_datetime(value)
            if not dt:
                d = parse_date(value)
                dt = datetime.datetime.combine(d, datetime.time.min) if d else None
        else:
            dt = None
        
        if dt and timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_default_timezone())
        return dt


class TeacherEventListView(DateParsingMixin, APIView):
    """
    GET /api/events/teacher/ - List events created by teacher
    POST /api/events/teacher/ - Create new event
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        # Get events created by this teacher or for their courses
        teacher_courses = Course.objects.filter(owner=user).values_list('id', flat=True)
        events = PlatformEvent.objects.filter(
            Q(created_by=user) | Q(course_id__in=teacher_courses)
        ).order_by('start_date')
        
        data = []
        for e in events:
            data.append({
                'id': str(e.id),
                'name': e.name,
                'description': e.description,
                'start_date': e.start_date.isoformat() if e.start_date else None,
                'end_date': e.end_date.isoformat() if e.end_date else None,
                'type': e.type,
                'status': e.status,
                'course_id': str(e.course_id) if e.course_id else None,
                'course_title': e.course.title if e.course else None,
                'notify_students': e.notify_students,
                'created_at': e.created_at.isoformat() if e.created_at else None,
            })
        return Response({'items': data}, status=status.HTTP_200_OK)

    def post(self, request):
        user = request.user
        data = request.data
        start_dt = self._parse_datetime(data.get('start_date'))
        end_dt = self._parse_datetime(data.get('end_date'))
        
        # Validate required fields
        name = data.get('name', '').strip()
        if not name:
            return Response({'detail': 'Tên sự kiện không được để trống'}, status=status.HTTP_400_BAD_REQUEST)
        
        if not start_dt:
            return Response({'detail': 'Thời gian bắt đầu không được để trống'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Create event
        event = PlatformEvent.objects.create(
            name=name,
            description=data.get('description', ''),
            start_date=start_dt,
            end_date=end_dt,
            type=data.get('type', 'other'),
            status='upcoming',
            created_by=user,
            course_id=data.get('course_id'),
            notify_students=data.get('notify_students', True),
        )
        
        # Send notifications to students if enabled
        if event.notify_students:
            self._notify_students(event, user)
        
        return Response({
            'id': str(event.id),
            'name': event.name,
            'message': 'Tạo sự kiện thành công'
        }, status=status.HTTP_201_CREATED)
    
    def _notify_students(self, event, teacher):
        """Send notifications to enrolled students"""
        students = []
        
        if event.course:
            # Notify students enrolled in specific course
            enrollments = Enrollment.objects.filter(course=event.course).select_related('student')
            students = [e.student for e in enrollments]
        else:
            # Notify students in all teacher's courses
            teacher_courses = Course.objects.filter(owner=teacher)
            enrollments = Enrollment.objects.filter(course__in=teacher_courses).select_related('student')
            students = list(set(e.student for e in enrollments))
        
        # Create notifications
        for student in students:
            Notification.objects.create(
                user=student,
                title=f"📅 Sự kiện mới: {event.name}",
                message=f"{event.description[:100]}..." if len(event.description) > 100 else event.description or f"Thời gian: {event.start_date.strftime('%d/%m/%Y %H:%M')}",
                type="info",
                category="event",
                metadata={
                    "event_id": str(event.id),
                    "event_type": event.type,
                    "start_date": event.start_date.isoformat(),
                    "course_id": str(event.course_id) if event.course_id else None,
                    "teacher_id": str(teacher.id),
                },
            )


class TeacherEventDetailView(DateParsingMixin, APIView):
    """
    GET /api/events/teacher/<id>/ - Get event detail
    PATCH /api/events/teacher/<id>/ - Update event
    DELETE /api/events/teacher/<id>/ - Delete event
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, event_id):
        try:
            event = PlatformEvent.objects.get(id=event_id, created_by=request.user)
        except PlatformEvent.DoesNotExist:
            return Response({'detail': 'Không tìm thấy sự kiện'}, status=status.HTTP_404_NOT_FOUND)
        
        return Response({
            'id': str(event.id),
            'name': event.name,
            'description': event.description,
            'start_date': event.start_date.isoformat() if event.start_date else None,
            'end_date': event.end_date.isoformat() if event.end_date else None,
            'type': event.type,
            'status': event.status,
            'course_id': str(event.course_id) if event.course_id else None,
            'notify_students': event.notify_students,
        }, status=status.HTTP_200_OK)

    def patch(self, request, event_id):
        try:
            event = PlatformEvent.objects.get(id=event_id, created_by=request.user)
        except PlatformEvent.DoesNotExist:
            return Response({'detail': 'Không tìm thấy sự kiện'}, status=status.HTTP_404_NOT_FOUND)
        
        data = request.data
        if 'name' in data:
            event.name = data['name']
        if 'description' in data:
            event.description = data['description']
        if 'start_date' in data:
            parsed_start = self._parse_datetime(data['start_date'])
            if parsed_start:
                event.start_date = parsed_start
        if 'end_date' in data:
            parsed_end = self._parse_datetime(data['end_date'])
            if parsed_end:
                event.end_date = parsed_end
        if 'type' in data:
            event.type = data['type']
        if 'status' in data:
            event.status = data['status']
        if 'course_id' in data:
            event.course_id = data['course_id']
        if 'notify_students' in data:
            event.notify_students = data['notify_students']
        
        event.save()
        
        return Response({
            'id': str(event.id),
            'message': 'Cập nhật sự kiện thành công'
        }, status=status.HTTP_200_OK)

    def delete(self, request, event_id):
        try:
            event = PlatformEvent.objects.get(id=event_id, created_by=request.user)
        except PlatformEvent.DoesNotExist:
            return Response({'detail': 'Không tìm thấy sự kiện'}, status=status.HTTP_404_NOT_FOUND)
        
        event.delete()
        return Response({'message': 'Xóa sự kiện thành công'}, status=status.HTTP_200_OK)


class UpcomingEventsView(APIView):
    """
    GET /api/events/upcoming/ - Get upcoming events for current user
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        now = timezone.now()
        
        # For teachers: get their created events
        # For students: get events from enrolled courses
        if user.role == 'instructor':
            events = PlatformEvent.objects.filter(
                created_by=user,
                start_date__gte=now,
                status='upcoming'
            ).order_by('start_date')[:10]
        else:
            # Student: get events from enrolled courses
            enrolled_courses = Enrollment.objects.filter(student=user).values_list('course_id', flat=True)
            events = PlatformEvent.objects.filter(
                Q(course_id__in=enrolled_courses) | Q(course__isnull=True),
                start_date__gte=now,
                status='upcoming'
            ).order_by('start_date')[:10]
        
        data = []
        for e in events:
            data.append({
                'id': str(e.id),
                'name': e.name,
                'start_date': e.start_date.isoformat() if e.start_date else None,
                'time': e.start_date.strftime('%I:%M %p') if e.start_date else '',
                'type': e.type,
                'course_title': e.course.title if e.course else None,
            })
        
        return Response({'items': data}, status=status.HTTP_200_OK)
