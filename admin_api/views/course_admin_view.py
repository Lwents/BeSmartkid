from django.db import transaction
from django.db.models import Q, Count
from django.core.paginator import Paginator
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from admin_api.permissions import IsAdmin
from admin_api.pagination import page_link, positive_int_query
from admin_api.services import record_admin_action
from content.models import Course, Subject, Lesson, Enrollment


def _course_status(course):
    if course.archived:
        return 'archived'
    return 'published' if course.published else 'draft'


class AdminCourseListView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        """List all courses with filtering and pagination"""
        # Get query parameters
        q = request.query_params.get('q', '')
        grade = request.query_params.get('grade')
        subject = request.query_params.get('subject')
        teacher_id = request.query_params.get('teacherId')
        status_filter = request.query_params.get('status')
        from_date = request.query_params.get('from')
        to_date = request.query_params.get('to')
        page = positive_int_query(request, 'page', 1)
        page_size = positive_int_query(
            request, 'pageSize', 20, aliases=('page_size',), maximum=100
        )

        # Build queryset
        queryset = Course.objects.select_related('subject', 'owner').prefetch_related('modules__lessons')

        # Apply filters
        if q:
            queryset = queryset.filter(
                Q(title__icontains=q) |
                Q(description__icontains=q)
            )

        if grade:
            queryset = queryset.filter(grade=grade)

        if subject:
            try:
                subject_obj = Subject.objects.get(slug=subject)
                queryset = queryset.filter(subject=subject_obj)
            except Subject.DoesNotExist:
                pass

        if teacher_id:
            queryset = queryset.filter(owner_id=teacher_id)

        if status_filter:
            if status_filter == 'published':
                queryset = queryset.filter(published=True, archived=False)
            elif status_filter == 'draft':
                queryset = queryset.filter(published=False, archived=False)
            elif status_filter == 'archived':
                queryset = queryset.filter(archived=True)

        # Date filtering using created_on field
        if from_date:
            queryset = queryset.filter(created_on__gte=from_date)
        if to_date:
            queryset = queryset.filter(created_on__lte=to_date)

        # Annotate with counts
        queryset = queryset.annotate(
            lessons_count=Count('modules__lessons', distinct=True),
            enrollments_count=Count('enrollments', distinct=True)
        ).order_by('-created_on', 'id')

        # Paginate
        paginator = Paginator(queryset, page_size)
        if page > max(paginator.num_pages, 1):
            return Response(
                {'page': 'Trang yêu cầu vượt quá số trang hiện có.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        page_obj = paginator.page(page)

        # Serialize
        items = []
        for course in page_obj:
            thumbnail_url = None
            if course.thumbnail:
                thumbnail_url = course.thumbnail.url if hasattr(course.thumbnail, 'url') else str(course.thumbnail)
            
            items.append({
                'id': str(course.id),
                'title': course.title,
                'grade': int(course.grade) if course.grade and str(course.grade).isdigit() else course.grade,
                'subject': course.subject.slug if course.subject else None,
                'subjectLabel': course.subject.title if course.subject else None,
                'teacherId': str(course.owner.id) if course.owner else None,
                'teacherName': course.owner.email if hasattr(course.owner, 'email') and course.owner.email else course.owner.username if course.owner else 'N/A',
                'lessonsCount': getattr(course, 'lessons_count', 0),
                'enrollments': getattr(course, 'enrollments_count', 0),
                'status': _course_status(course),
                'createdAt': course.created_on.isoformat() if getattr(course, 'created_on', None) else None,
                'updatedAt': course.updated_on.isoformat() if getattr(course, 'updated_on', None) else None,
                'thumbnail': thumbnail_url
            })

        return Response({
            'results': items,
            'items': items,
            'count': paginator.count,
            'total': paginator.count,
            'page': page,
            'page_size': page_size,
            'total_pages': paginator.num_pages,
            'next': page_link(request, page + 1) if page_obj.has_next() else None,
            'previous': page_link(request, page - 1) if page_obj.has_previous() else None,
        }, status=status.HTTP_200_OK)


class AdminCourseDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request, pk):
        """Get course detail"""
        try:
            course = Course.objects.select_related('subject', 'owner').prefetch_related(
                'modules__lessons'
            ).get(id=pk)
        except Course.DoesNotExist:
            return Response({'error': 'Course not found'}, status=status.HTTP_404_NOT_FOUND)

        # Build sections (modules)
        sections = []
        for module in course.modules.all().order_by('position'):
            lessons = []
            for lesson in module.lessons.all().order_by('position'):
                lessons.append({
                    'id': str(lesson.id),
                    'title': lesson.title,
                    'type': lesson.content_type,
                    'published': lesson.published,
                    'hasVideo': bool(lesson.video_file or lesson.video_url),
                    'videoSource': 'file' if lesson.video_file else (
                        'link' if lesson.video_url else ''
                    ),
                })
            sections.append({
                'id': str(module.id),
                'title': module.title,
                'order': module.position,
                'lessons': lessons
            })

        # Get enrollment count
        enrollments_count = Enrollment.objects.filter(course=course).count()
        
        # Get thumbnail URL
        thumbnail_url = None
        if course.thumbnail:
            thumbnail_url = course.thumbnail.url if hasattr(course.thumbnail, 'url') else str(course.thumbnail)

        return Response({
            'id': str(course.id),
            'title': course.title,
            'description': course.description or '',
            'grade': int(course.grade) if course.grade and course.grade.isdigit() else None,
            'subject': course.subject.slug if course.subject else None,
            'teacherId': str(course.owner.id) if course.owner else None,
            'teacherName': course.owner.email if course.owner else 'N/A',
            'lessonsCount': sum(len(s['lessons']) for s in sections),
            'enrollments': enrollments_count,
            'status': _course_status(course),
            'createdAt': course.created_on.isoformat() if getattr(course, 'created_on', None) else None,
            'updatedAt': course.updated_on.isoformat() if getattr(course, 'updated_on', None) else None,
            'thumbnail': thumbnail_url,
            'sections': sections
        }, status=status.HTTP_200_OK)

class AdminLessonVideoDeleteView(APIView):
    """Allow admins to remove a lesson video without deleting the lesson itself."""
    permission_classes = [IsAuthenticated, IsAdmin]

    @transaction.atomic
    def delete(self, request, pk, lesson_id):
        try:
            lesson = Lesson.objects.select_related('module__course').get(
                id=lesson_id,
                module__course_id=pk,
            )
        except Lesson.DoesNotExist:
            return Response(
                {'detail': 'Không tìm thấy video trong khóa học này.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not lesson.video_file and not lesson.video_url:
            return Response(
                {'detail': 'Bài học này không còn video để xóa.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        removed_source = str(lesson.video_file or lesson.video_url or '')
        if lesson.video_file:
            lesson.video_file.delete(save=False)
        lesson.video_file = None
        lesson.video_url = None
        lesson.video_transcript = None
        update_fields = ['video_file', 'video_url', 'video_transcript']

        # Video lessons without a video must not remain visible to students.
        if lesson.content_type == 'video' and lesson.published:
            lesson.published = False
            update_fields.append('published')
        lesson.save(update_fields=update_fields)

        record_admin_action(
            request=request,
            action='lesson.video.delete',
            target_type='lesson',
            target_id=lesson.id,
            details={
                'courseId': str(pk),
                'lessonTitle': lesson.title,
                'source': removed_source,
            },
        )
        return Response({
            'success': True,
            'lessonId': str(lesson.id),
            'published': lesson.published,
        }, status=status.HTTP_200_OK)
