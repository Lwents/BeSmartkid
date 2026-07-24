from django.db.models import Q, Count
from django.core.paginator import Paginator
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from admin_api.permissions import IsAdmin
from content.models import Course, Subject, Module, Lesson, Enrollment
from custom_account.models import UserModel


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
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('pageSize', 20))

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
                queryset = queryset.filter(published=True)
            elif status_filter == 'draft':
                queryset = queryset.filter(published=False)
            # Add more status filters as needed

        # Date filtering using created_on field
        if from_date:
            queryset = queryset.filter(created_on__gte=from_date)
        if to_date:
            queryset = queryset.filter(created_on__lte=to_date)

        # Annotate with counts
        queryset = queryset.annotate(
            lessons_count=Count('modules__lessons', distinct=True),
            enrollments_count=Count('enrollments', distinct=True)
        )

        # Paginate
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)

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
                'status': 'published' if course.published else 'draft',
                'createdAt': course.created_on.isoformat() if getattr(course, 'created_on', None) else None,
                'updatedAt': course.updated_on.isoformat() if getattr(course, 'updated_on', None) else None,
                'thumbnail': thumbnail_url
            })

        return Response({
            'items': items,
            'total': paginator.count
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
                    'durationMinutes': None,  # Placeholder
                    'isPreview': False  # Placeholder
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
            'status': 'published' if course.published else 'draft',
            'createdAt': course.created_on.isoformat() if getattr(course, 'created_on', None) else None,
            'updatedAt': course.updated_on.isoformat() if getattr(course, 'updated_on', None) else None,
            'thumbnail': thumbnail_url,
            'level': None,  # Placeholder
            'durationMinutes': None,  # Placeholder
            'sections': sections
        }, status=status.HTTP_200_OK)

    def delete(self, request, pk):
        """Delete a course (admin only). Cascades to modules/lessons/enrollments."""
        try:
            course = Course.objects.get(id=pk)
        except Course.DoesNotExist:
            return Response({'error': 'Course not found'}, status=status.HTTP_404_NOT_FOUND)

        course.delete()
        return Response({'success': True}, status=status.HTTP_204_NO_CONTENT)


class AdminCourseApproveView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, pk):
        """Approve a course"""
        try:
            course = Course.objects.get(id=pk)
        except Course.DoesNotExist:
            return Response({'error': 'Course not found'}, status=status.HTTP_404_NOT_FOUND)

        course.published = True
        course.save()

        return Response({'success': True}, status=status.HTTP_200_OK)


class AdminCourseRejectView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, pk):
        """Reject a course"""
        try:
            course = Course.objects.get(id=pk)
        except Course.DoesNotExist:
            return Response({'error': 'Course not found'}, status=status.HTTP_404_NOT_FOUND)

        # Could add a rejection reason field
        course.published = False
        course.save()

        return Response({'success': True}, status=status.HTTP_200_OK)


class AdminCoursePublishView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, pk):
        """Publish a course"""
        try:
            course = Course.objects.get(id=pk)
        except Course.DoesNotExist:
            return Response({'error': 'Course not found'}, status=status.HTTP_404_NOT_FOUND)

        course.published = True
        course.save()

        return Response({'success': True}, status=status.HTTP_200_OK)


class AdminCourseUnpublishView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, pk):
        """Unpublish a course"""
        try:
            course = Course.objects.get(id=pk)
        except Course.DoesNotExist:
            return Response({'error': 'Course not found'}, status=status.HTTP_404_NOT_FOUND)

        course.published = False
        course.save()

        return Response({'success': True}, status=status.HTTP_200_OK)


class AdminCourseArchiveView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, pk):
        """Archive a course"""
        try:
            course = Course.objects.get(id=pk)
        except Course.DoesNotExist:
            return Response({'error': 'Course not found'}, status=status.HTTP_404_NOT_FOUND)

        # Could add an archived field
        course.published = False
        course.save()

        return Response({'success': True}, status=status.HTTP_200_OK)


class AdminCourseRestoreView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, pk):
        """Restore an archived course"""
        try:
            course = Course.objects.get(id=pk)
        except Course.DoesNotExist:
            return Response({'error': 'Course not found'}, status=status.HTTP_404_NOT_FOUND)

        # Restore logic
        course.published = True
        course.save()

        return Response({'success': True}, status=status.HTTP_200_OK)


class AdminCourseBulkActionView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request):
        """Bulk actions on courses"""
        action = request.data.get('action')  # approve, reject, publish, archive
        ids = request.data.get('ids', [])

        if not ids:
            return Response({'error': 'No IDs provided'}, status=status.HTTP_400_BAD_REQUEST)

        courses = Course.objects.filter(id__in=ids)

        if action == 'approve':
            courses.update(published=True)
        elif action == 'reject':
            courses.update(published=False)
        elif action == 'publish':
            courses.update(published=True)
        elif action == 'archive':
            courses.update(published=False)
        else:
            return Response({'error': 'Invalid action'}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'success': True, 'count': courses.count()}, status=status.HTTP_200_OK)


