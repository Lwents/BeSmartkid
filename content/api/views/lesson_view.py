"""
Lesson API: CRUD bài học trong module, publish, transcribe video, và xử lý upload file.
Liên kết FE: contentService.*Lesson* (FE gọi /content/modules/:moduleId/lessons/, /content/lessons/:id/...).
"""
from typing import Any, Dict
from django.db import transaction
from django.shortcuts import get_object_or_404

from rest_framework import generics, status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from custom_account.api.permissions import IsOwnerOrAdmin
from content import models
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
from content.utils.storage_utils import local_path_from_storage

# Create service instances
lesson_service = LessonService()
MAX_VIDEO_BYTES = 500 * 1024 * 1024


def _auto_transcribe_if_needed(lesson_model):
    """
    Tự động tạo transcript cho lesson nếu có video nhưng chưa có transcript.
    Chạy trong background (async) để không block response.
    """
    # Kiểm tra có video không
    has_video = bool(lesson_model.video_url or lesson_model.video_file)
    
    # Kiểm tra đã có transcript chưa
    has_transcript = bool(lesson_model.video_transcript and lesson_model.video_transcript.strip())
    
    if has_video and not has_transcript:
        # Tự động transcribe trong background
        import threading
        import logging
        logger = logging.getLogger(__name__)
        
        def transcribe_in_background():
            try:
                from content.services.video_transcriber import video_transcriber
                
                # Refresh lesson từ DB để đảm bảo có dữ liệu mới nhất
                lesson_model.refresh_from_db()
                
                # Transcribe
                if lesson_model.video_file:
                    with local_path_from_storage(str(lesson_model.video_file)) as video_path:
                        if not video_path:
                            return
                        transcript = video_transcriber.transcribe_video(video_path=video_path)
                elif lesson_model.video_url:
                    transcript = video_transcriber.transcribe_video(video_url=lesson_model.video_url)
                else:
                    return
                
                # Lưu transcript nếu có
                if transcript:
                    lesson_model.video_transcript = transcript
                    lesson_model.save(update_fields=['video_transcript'])
                    logger.info(f"Auto-transcribed lesson {lesson_model.id}: {len(transcript)} characters")
            except Exception as e:
                logger.warning(f"Auto-transcribe failed for lesson {lesson_model.id}: {e}")
        
        # Chạy trong thread riêng để không block response
        thread = threading.Thread(target=transcribe_in_background, daemon=True)
        thread.start()


def _ensure_published_version(lesson_model, author_id=None):
    """
    Make sure a lesson has at least one published version so course publish rule can pass.
    Used for legacy lessons that might not have versions yet.
    """
    from content.models import LessonVersion
    if lesson_model.versions.exists():
        return
    author = None
    if author_id:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        author = User.objects.filter(id=author_id).first()
    LessonVersion.objects.create(
        lesson=lesson_model,
        version=1,
        status='published',
        author=author,
        content={"structure": "lesson", "content_blocks": []},
    )

class LessonListCreateView(generics.ListCreateAPIView):
    """
    GET /api/modules/{module_id}/lessons/
    POST /api/modules/{module_id}/lessons/
    """
    serializer_class = LessonSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    parser_classes = [MultiPartParser, FormParser, JSONParser]  # Cho phép upload file

    def get_queryset(self):
        module_id = self.kwargs.get("module_id")
        return models.Lesson.objects.filter(module_id=module_id)

    def create(self, request, module_id=None, *args, **kwargs):
        # Merge module_id from URL into data if not provided
        data = request.data.copy()
        if module_id and 'module' not in data:
            data['module'] = module_id
        
        # Remove empty file fields
        for field in ['video_file']:
            if field in data:
                value = data[field]
                if value == '' or value is None or (hasattr(value, 'name') and not value.name):
                    data.pop(field, None)
        
        serializer = CreateLessonInputSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        # Convert to CreateLessonDomain
        from content.domains.lesson_domain import CreateLessonDomain
        cmd = CreateLessonDomain(
            module_id=str(module_id) if module_id else str(serializer.validated_data.get('module').id),
            title=serializer.validated_data['title'],
            position=serializer.validated_data.get('position', 0),
            content_type=serializer.validated_data.get('content_type', 'lesson')
        )
        # Truyền author_id nếu có user đăng nhập
        author_id = request.user.id if request.user.is_authenticated else None
        try:
            created_domain = lesson_service.create_lesson(cmd, author_id=author_id)
        except Exception as e:
            import traceback
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error creating lesson: {str(e)}\n{traceback.format_exc()}")
            return Response(
                {"detail": f"Error creating lesson: {str(e)}"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # Update model with new fields
        from content.models import Lesson
        try:
            lesson_model = Lesson.objects.prefetch_related('versions').get(id=created_domain.id)
            # Ensure a default published version exists (legacy safety)
            _ensure_published_version(lesson_model, author_id=author_id)
            if 'introduction' in data:
                lesson_model.introduction = data['introduction']
            if 'video_url' in data:
                lesson_model.video_url = data['video_url']
            if 'video_file' in request.FILES and request.FILES['video_file']:
                video_file = request.FILES['video_file']
                if getattr(video_file, 'size', 0) > MAX_VIDEO_BYTES:
                    return Response(
                        {"detail": "File video tối đa 500MB."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                lesson_model.video_file = video_file
            if 'document_file' in request.FILES and request.FILES['document_file']:
                lesson_model.document_file = request.FILES['document_file']
            if 'text_content' in data:
                lesson_model.text_content = data['text_content']
            if 'requires_exercise_completion' in data:
                lesson_model.requires_exercise_completion = bool(data['requires_exercise_completion'])
            # Nếu có published trong request, dùng giá trị đó, nếu không thì giữ mặc định True từ service
            if 'published' in data:
                lesson_model.published = bool(data['published'])
            lesson_model.save()
        except Exception as e:
            import traceback
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error updating lesson fields: {str(e)}\n{traceback.format_exc()}")
            # Vẫn trả về lesson đã tạo được, chỉ cảnh báo
            lesson_model = Lesson.objects.prefetch_related('versions').get(id=created_domain.id)
        
        # Tự động tạo transcript nếu có video nhưng chưa có transcript
        _auto_transcribe_if_needed(lesson_model)
        
        # Return with new fields
        from content.domains.lesson_domain import LessonDomain
        lesson_domain = LessonDomain.from_model(lesson_model)
        result = LessonSerializer.from_domain(lesson_domain)
        from django.conf import settings
        if lesson_model.video_file:
            result['video_file'] = f"{settings.MEDIA_URL}{lesson_model.video_file}" if not str(lesson_model.video_file).startswith('http') else str(lesson_model.video_file)
        return Response(result, status=status.HTTP_201_CREATED)


class LessonDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET /api/lessons/{id}/
    PATCH /api/lessons/{id}/   (owner/admin)
    DELETE /api/lessons/{id}/
    """
    queryset = models.Lesson.objects.all()
    serializer_class = LessonSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    parser_classes = [MultiPartParser, FormParser, JSONParser]  # Cho phép upload file

    def check_object_permissions(self, request, obj):
        """
        Override to check if user is owner of the course (via module) or admin.
        """
        if request.method in permissions.SAFE_METHODS:
            # Allow read for all authenticated users
            if not request.user or not request.user.is_authenticated:
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied("Authentication required")
            return
        
        # For write/delete, check if user is owner of course or admin
        if request.user.is_staff or request.user.is_superuser:
            return
        
        # Check if user is owner of the course (lesson -> module -> course -> owner)
        if hasattr(obj, 'module') and obj.module and hasattr(obj.module, 'course'):
            course = obj.module.course
            if hasattr(course, 'owner') and course.owner == request.user:
                return
            elif hasattr(course, 'owner_id') and course.owner_id == request.user.id:
                return
        
        # Default deny
        from rest_framework.exceptions import PermissionDenied
        raise PermissionDenied("You do not have permission to perform this action")

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", True)
        instance = self.get_object()
        
        # Handle FormData for file uploads
        if hasattr(request.data, 'copy'):
            data = request.data.copy()
        else:
            data = dict(request.data)
        
        # Remove empty file fields
        for field in ['video_file', 'document_file']:
            if field in data:
                value = data[field]
                if value == '' or value is None or (hasattr(value, 'name') and not value.name):
                    data.pop(field, None)
        
        serializer = self.get_serializer(instance, data=data, partial=partial)
        serializer.is_valid(raise_exception=True)
        updates = serializer.validated_data
        
        # Update model directly for new fields
        # Ensure a default published version exists (legacy safety)
        _ensure_published_version(instance, author_id=request.user.id if request.user.is_authenticated else None)
        if 'introduction' in updates:
            instance.introduction = updates['introduction']
        if 'video_url' in updates:
            instance.video_url = updates['video_url']
        if 'video_file' in request.FILES and request.FILES['video_file']:
            video_file = request.FILES['video_file']
            if getattr(video_file, 'size', 0) > MAX_VIDEO_BYTES:
                return Response(
                    {"detail": "File video tối đa 500MB."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            instance.video_file = video_file
        if 'document_file' in request.FILES and request.FILES['document_file']:
            instance.document_file = request.FILES['document_file']
        if 'text_content' in updates:
            instance.text_content = updates['text_content']
        if 'requires_exercise_completion' in updates:
            instance.requires_exercise_completion = updates['requires_exercise_completion']
        if 'video_transcript' in updates:
            instance.video_transcript = updates['video_transcript']
        instance.save()
        
        # Also update via service for domain logic (convert dict to UpdateLessonDomain)
        from content.domains.lesson_domain import UpdateLessonDomain
        update_domain = UpdateLessonDomain(
            title=updates.get('title'),
            position=updates.get('position'),
            content_type=updates.get('content_type')
        )
        updated_domain = lesson_service.update_lesson(lesson_id=instance.id, update_data=update_domain)
        if not updated_domain:
            return Response({"detail": "Cannot update lesson"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Tự động tạo transcript nếu có video nhưng chưa có transcript
        # (không chỉ khi video thay đổi, mà cả khi update lesson đã có video nhưng chưa có transcript)
        _auto_transcribe_if_needed(instance)
        
        # Return updated model data
        from content.domains.lesson_domain import LessonDomain
        lesson_domain = LessonDomain.from_model(instance)
        result = LessonSerializer.from_domain(lesson_domain)
        # Add file URLs
        from django.conf import settings
        if instance.video_file:
            result['video_file'] = f"{settings.MEDIA_URL}{instance.video_file}" if not str(instance.video_file).startswith('http') else str(instance.video_file)
        return Response(result)


class LessonPublishView(APIView):
    """
    POST /api/lessons/{id}/publish/
    body example: {"published": true}
    """
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]

    def post(self, request, lesson_id: str):
        published_flag = request.data.get("published", True)
        try:
            # Get lesson to find latest version
            lesson = models.Lesson.objects.get(id=lesson_id)
            # Get latest version or use 1
            latest_version = lesson.versions.order_by('-version').first()
            version = latest_version.version if latest_version else 1
            # Convert to PublishLessonDomain
            from content.domains.lesson_domain import PublishLessonDomain
            publish_domain = PublishLessonDomain(
                lesson_id=lesson_id,
                version=version
            )
            updated = lesson_service.publish_lesson(lesson_id=lesson_id, publish_data=publish_domain)
            if not updated:
                return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
            return Response(LessonSerializer.from_domain(updated))
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class LessonTranscribeView(APIView):
    """
    POST /api/lessons/{id}/transcribe/
    Tự động tạo transcript từ video của bài học
    """
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]

    def post(self, request, lesson_id: str):
        try:
            lesson = models.Lesson.objects.get(id=lesson_id)
            
            # Kiểm tra có video không
            video_url = lesson.video_url
            video_file = lesson.video_file
            
            if not video_url and not video_file:
                return Response(
                    {"detail": "Bài học không có video"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Import transcriber
            from content.services.video_transcriber import video_transcriber
            
            # Transcribe
            if video_file:
                with local_path_from_storage(str(video_file)) as video_path:
                    transcript = video_transcriber.transcribe_video(video_path=video_path) if video_path else None
            else:
                transcript = video_transcriber.transcribe_video(video_url=video_url)
            
            if not transcript:
                return Response(
                    {"detail": "Không thể tạo transcript. Hiện chỉ hỗ trợ phụ đề YouTube nếu có."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            # Lưu transcript
            lesson.video_transcript = transcript
            lesson.save(update_fields=['video_transcript'])
            
            return Response({
                "success": True,
                "message": "Đã tạo transcript thành công",
                "transcript": transcript[:500] + "..." if len(transcript) > 500 else transcript,
                "full_length": len(transcript)
            })
            
        except models.Lesson.DoesNotExist:
            return Response({"detail": "Không tìm thấy bài học"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as exc:
            import traceback
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Transcribe error: {exc}\n{traceback.format_exc()}")
            return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
