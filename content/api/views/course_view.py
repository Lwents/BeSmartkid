"""
Course API: list/create/update/publish khoá học, enroll/unenroll học viên.
Liên kết FE: courseService.* (FE gọi /content/courses/, /admin/courses/..., /student/courses/).
"""
from typing import Any, Dict
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404

from rest_framework import generics, status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from custom_account.api.permissions import IsOwnerOrAdmin
from content import models
from content.models import Course
from content.serializers import (
    SubjectSerializer, CourseSerializer, ModuleSerializer, LessonSerializer,
    LessonVersionSerializer, ContentBlockSerializer, ExplorationSerializer,
    ExplorationStateSerializer, ExplorationTransitionSerializer,
    CreateCourseInputSerializer, AddModuleInputSerializer, CreateLessonInputSerializer,
    CreateLessonVersionInputSerializer, PublishLessonVersionInputSerializer,
    AddContentBlockInputSerializer, CreateExplorationInputSerializer,
    AddExplorationStateInputSerializer, AddExplorationTransitionInputSerializer,
    CourseDetailReadSerializer, ModuleReadSerializer, LessonReadSerializer,
    LessonVersionReadSerializer
)

from content.services.subject_service import SubjectService
from content.services.course_service import CourseService
from content.services.module_service import ModuleService
from content.services.lesson_service import LessonService
from content.services.lesson_version_service import LessonVersionService
from content.services.content_block_service import ContentBlockService
from content.services.exploration_service import (
    ExplorationService, ExplorationStateService, ExplorationTransitionService
)
from content.domains.course_domain import CourseDomain

# Create service instances
course_service = CourseService()
MAX_THUMBNAIL_BYTES = 5 * 1024 * 1024
MAX_VIDEO_BYTES = 500 * 1024 * 1024



class CourseListCreateView(generics.ListCreateAPIView):
    """
    GET /api/courses/?subject_id=&published=      -> list (public)
    POST /api/courses/                             -> create (auth)
    """
    serializer_class = CourseSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    parser_classes = [MultiPartParser, FormParser, JSONParser]  # Cho phép upload file khi tạo mới

    def get_queryset(self):
        qs = models.Course.objects.all()
        
        # For students, only show published courses
        if self.request.user.is_authenticated:
            user_role = getattr(self.request.user, 'role', None)
            if user_role == 'student':
                # Students can only see published courses
                qs = qs.filter(published=True)
            elif user_role == 'instructor' and not self.request.user.is_staff:
                # Instructors see only their own courses (both published and unpublished)
                qs = qs.filter(owner=self.request.user)
        else:
            # Unauthenticated users can only see published courses
            qs = qs.filter(published=True)
        
        subject_id = self.request.query_params.get("subject_id")
        published = self.request.query_params.get("published")
        if subject_id:
            qs = qs.filter(subject_id=subject_id)
        # Allow explicit published filter for instructors/admins (override default for students)
        if published is not None:
            # Only allow this filter for non-student users
            user_role = getattr(self.request.user, 'role', None) if self.request.user.is_authenticated else None
            if user_role != 'student' or self.request.user.is_staff:
                qs = qs.filter(published=(published.lower() == "true"))
        
        # Search by title/description
        q = self.request.query_params.get("q") or self.request.query_params.get("search")
        if q:
            qs = qs.filter(
                Q(title__icontains=q) |
                Q(description__icontains=q) |
                Q(introduction__icontains=q)
            )
        
        # Annotate enrollments count for performance
        from django.db.models import Count
        qs = qs.annotate(enrollments_count=Count('enrollments'))
        
        return qs

    def create(self, request, *args, **kwargs):
        try:
            # Handle FormData - create a mutable copy
            if hasattr(request.data, 'copy'):
                data = request.data.copy()
            else:
                data = dict(request.data)
            
            # Remove empty file fields from data to avoid validation errors
            # FormData sends empty strings for file fields when not provided
            for field in ['thumbnail', 'video_file']:
                if field in data:
                    value = data[field]
                    if value == '' or value is None or (hasattr(value, 'name') and not value.name):
                        data.pop(field, None)
            
            # Handle video_url - remove if empty
            if 'video_url' in data and (data['video_url'] == '' or data['video_url'] is None):
                data.pop('video_url', None)
            
            serializer = CreateCourseInputSerializer(data=data)
            serializer.is_valid(raise_exception=True)
            validated_data = serializer.validated_data
            
            # Convert to CreateCourseDomain
            from content.domains.course_domain import CreateCourseDomain
            subject = validated_data.get("subject")
            cmd = CreateCourseDomain(
                title=validated_data["title"],
                subject_id=str(subject.id) if subject else None,
                description=validated_data.get("description"),
                introduction=validated_data.get("introduction"),
                grade=validated_data.get("grade"),
                owner_id=request.user.id if request.user.is_authenticated else None,
                slug=validated_data.get("slug"),
                video_url=validated_data.get("video_url") or None,
                price=float(validated_data.get("price", 0) or 0)
            )
            
            # Create course
            created_domain = course_service.create_course(cmd)
            
            # Update course model with file uploads (only if files are actually provided)
            course_model = Course.objects.get(id=created_domain.id)
            file_updated = False
            if 'thumbnail' in request.FILES and request.FILES['thumbnail']:
                # Optimize image before saving
                from content.utils.image_optimizer import optimize_image
                thumbnail_file = request.FILES['thumbnail']
                if getattr(thumbnail_file, 'size', 0) > MAX_THUMBNAIL_BYTES:
                    return Response(
                        {"detail": "Ảnh khóa học tối đa 5MB."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                optimized_thumbnail = optimize_image(
                    thumbnail_file,
                    max_width=1200,
                    max_height=800,
                    quality=85,
                    format='JPEG'
                )
                # Use optimized version if available, otherwise use original
                course_model.thumbnail = optimized_thumbnail if optimized_thumbnail else thumbnail_file
                file_updated = True
            if 'video_file' in request.FILES and request.FILES['video_file']:
                video_file = request.FILES['video_file']
                if getattr(video_file, 'size', 0) > MAX_VIDEO_BYTES:
                    return Response(
                        {"detail": "File video khóa học tối đa 500MB."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                course_model.video_file = video_file
                file_updated = True
            
            if file_updated:
                course_model.save()
                # Refresh from database to get the saved file paths (not file objects)
                course_model.refresh_from_db()
            
            # Convert to domain for response - this will convert file fields to strings
            created_domain = CourseDomain.from_model(course_model)
            
            # Use serializer to properly format the response
            return Response(CourseDetailReadSerializer.from_domain(created_domain), status=status.HTTP_201_CREATED)
        except Exception as e:
            import traceback
            from content.services.exceptions import DomainValidationError
            from rest_framework.exceptions import ValidationError as DRFValidationError

            # Lỗi validation của serializer (thiếu title, sai kiểu...) -> để DRF trả 400 chuẩn
            if isinstance(e, DRFValidationError):
                raise

            error_detail = str(e)

            # Nếu là lỗi validation (ví dụ: tên khóa học trùng), trả về 400
            if isinstance(e, DomainValidationError):
                return Response(
                    {"detail": error_detail},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            traceback_str = traceback.format_exc()
            # Log error for debugging
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error creating course: {error_detail}\n{traceback_str}")
            return Response(
                {"detail": f"Error creating course: {error_detail}"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CourseDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET /api/courses/{id}/     -> public read, authenticated can read
    PATCH /api/courses/{id}/   (owner or admin)
    DELETE /api/courses/{id}/  (owner or admin)
    """
    queryset = models.Course.objects.all()
    serializer_class = CourseSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    parser_classes = [MultiPartParser, FormParser, JSONParser]  # Cho phép upload file
    
    def get_object(self):
        """Override to check if student can access unpublished courses"""
        obj = super().get_object()
        # Check if user is student trying to access unpublished course
        if self.request.user.is_authenticated:
            user_role = getattr(self.request.user, 'role', None)
            if user_role == 'student' and not obj.published:
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied("This course is not available yet.")
        elif not obj.published:
            # Unauthenticated users cannot see unpublished courses
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("This course is not available yet.")
        return obj
    
    def check_object_permissions(self, request, obj):
        """
        Override to allow read for all authenticated users, but restrict write/delete to owner or admin.
        """
        if request.method in permissions.SAFE_METHODS:
            # Allow read for all authenticated users (but unpublished courses are blocked in get_object)
            if not request.user or not request.user.is_authenticated:
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied("Authentication required")
            return
        # For write/delete, check IsOwnerOrAdmin
        permission = IsOwnerOrAdmin()
        if not permission.has_object_permission(request, self, obj):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You do not have permission to perform this action")

    def destroy(self, request, *args, **kwargs):
        """Override destroy to ensure proper permission check and error handling"""
        instance = self.get_object()
        try:
            # Permission is already checked in check_object_permissions
            instance.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return Response(
                {"detail": f"Error deleting course: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", True)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        updates = serializer.validated_data
        # Convert dict to UpdateCourseDomain
        from content.domains.course_domain import UpdateCourseDomain
        # Handle published field
        published = updates.get('published')
        if published is not None and isinstance(published, str):
            # Handle string "true"/"false" from FormData
            published = published.lower() == 'true'
        elif published is not None and isinstance(published, bool):
            pass  # Already boolean
        else:
            published = None
        
        update_domain = UpdateCourseDomain(
            title=updates.get('title'),
            description=updates.get('description'),
            grade=updates.get('grade'),
            slug=updates.get('slug'),
            subject_id=str(updates.get('subject').id) if updates.get('subject') else None,
            introduction=updates.get('introduction'),
            price=float(updates.get('price')) if updates.get('price') is not None else None,
            published=published
        )
        updated_domain = course_service.update_course(course_id=instance.id, update_data=update_domain)
        if not updated_domain:
            return Response({"detail": "Not found or cannot update"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Also handle file uploads if provided
        if 'thumbnail' in request.FILES and request.FILES['thumbnail']:
            # Optimize image before saving
            from content.utils.image_optimizer import optimize_image
            thumbnail_file = request.FILES['thumbnail']
            if getattr(thumbnail_file, 'size', 0) > MAX_THUMBNAIL_BYTES:
                return Response(
                    {"detail": "Ảnh khóa học tối đa 5MB."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            optimized_thumbnail = optimize_image(
                thumbnail_file,
                max_width=1200,
                max_height=800,
                quality=85,
                format='JPEG'
            )
            # Use optimized version if available, otherwise use original
            instance.thumbnail = optimized_thumbnail if optimized_thumbnail else thumbnail_file
        if 'video_file' in request.FILES and request.FILES['video_file']:
            video_file = request.FILES['video_file']
            if getattr(video_file, 'size', 0) > MAX_VIDEO_BYTES:
                return Response(
                    {"detail": "File video khóa học tối đa 500MB."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            instance.video_file = video_file
        if 'thumbnail' in request.FILES or 'video_file' in request.FILES:
            instance.save()
            updated_domain = CourseDomain.from_model(instance)
        
        return Response(CourseDetailReadSerializer.from_domain(updated_domain))


class CoursePublishView(APIView):
    """
    POST /api/courses/{id}/publish/
    body: {"require_all_lessons_published": false}  OR {"published": true}
    - Orchestrates domain-level checks (CourseDomain.can_publish)
    """
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]

    def post(self, request, course_id: str):
        # Handle both "require_all_lessons_published" and "published" in request
        # Frontend may send {"published": true}, backend also supports {"require_all_lessons_published": false}
        require_all = request.data.get("require_all_lessons_published", False)
        # If published is explicitly False, don't publish
        published_flag = request.data.get("published", True)
        if published_flag is False or published_flag == "false":
            # Unpublish instead
            course = Course.objects.get(id=course_id)
            course.published = False
            course.save()
            updated = course_service.get_course(course_id)
            return Response(CourseDetailReadSerializer.from_domain(updated))
        
        # get current domain via service
        course_domain = course_service.get_course(course_id)
        if not course_domain:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        try:
            # domain has publish() with rule enforcement; we call service to persist
            from content.domains.course_domain import CoursePublishDomain
            publish_domain = CoursePublishDomain(
                course_id=course_id,
                require_all_lessons_published=require_all
            )
            course_service.publish_course(course_id=course_id, publish_data=publish_domain)
            # fetch updated
            updated = course_service.get_course(course_id)
            return Response(CourseDetailReadSerializer.from_domain(updated))
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


# Extra: enroll / progress endpoints (basic)
class CourseEnrollView(APIView):
    """
    POST /api/courses/{id}/enroll/ -> enroll current user
    DELETE /api/courses/{id}/enroll/ -> unenroll
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, course_id: str):
        # Using course_service.enroll_user (if implemented)
        try:
            course = course_service.get_course(course_id)
            if not course:
                return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
            
            # Check if course is published (students can only enroll in published courses)
            user_role = getattr(request.user, 'role', None)
            if user_role == 'student' and not course.published:
                return Response(
                    {"detail": "Cannot enroll in unpublished course"}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            course_service.enroll_user(course_id=course_id, user_id=request.user.id)
            return Response({"success": True}, status=status.HTTP_200_OK)
        except AttributeError:
            # service not implemented: graceful decline
            return Response({"detail": "Enroll feature not implemented"}, status=status.HTTP_501_NOT_IMPLEMENTED)
        except Exception as ex:
            return Response({"detail": str(ex)}, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, course_id: str):
        try:
            course_service.unenroll_user(course_id=course_id, user_id=request.user.id)
            return Response({"success": True}, status=status.HTTP_200_OK)
        except AttributeError:
            return Response({"detail": "Unenroll feature not implemented"}, status=status.HTTP_501_NOT_IMPLEMENTED)
        except Exception as ex:
            return Response({"detail": str(ex)}, status=status.HTTP_400_BAD_REQUEST)
