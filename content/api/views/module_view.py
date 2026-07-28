"""
Module API: list/create modules trong khoá học, chỉnh sửa/xoá và reorder vị trí.
Liên kết FE: contentService.*Modules (FE gọi /content/courses/:courseId/modules/...).
"""
from typing import Any, Dict
from django.db import transaction
from django.shortcuts import get_object_or_404

from rest_framework import generics, status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response

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
from content.api.access import require_course_manager, require_course_viewer

# Create service instances
module_service = ModuleService()

class ModuleListCreateView(generics.ListCreateAPIView):
    """
    GET /api/courses/{course_id}/modules/
    POST /api/courses/{course_id}/modules/
    """
    serializer_class = ModuleSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        course_id = self.kwargs.get("course_id")
        course = get_object_or_404(models.Course, id=course_id)
        require_course_viewer(self.request.user, course)
        return models.Module.objects.filter(course_id=course_id)

    def create(self, request, course_id=None, *args, **kwargs):
        course = get_object_or_404(models.Course, id=course_id)
        require_course_manager(request.user, course)
        # Merge course_id from URL into data if not provided
        data = request.data.copy()
        if course_id and 'course' not in data:
            data['course'] = course_id
        serializer = AddModuleInputSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        cmd = serializer.to_domain(course_id=course_id)
        created_domain = module_service.create_module(cmd)
        return Response(ModuleSerializer.from_domain(created_domain), status=status.HTTP_201_CREATED)


class ModuleDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET /api/modules/{id}/
    PATCH /api/modules/{id}/   (owner/admin)
    DELETE /api/modules/{id}/
    """
    queryset = models.Module.objects.all()
    serializer_class = ModuleSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_object(self):
        obj = get_object_or_404(
            models.Module.objects.select_related("course"),
            id=self.kwargs.get("pk"),
        )
        if self.request.method in permissions.SAFE_METHODS:
            require_course_viewer(self.request.user, obj.course)
        else:
            require_course_manager(self.request.user, obj.course)
        return obj

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", True)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        updates = serializer.validated_data
        from content.domains.module_domain import UpdateModuleDomain
        update_domain = UpdateModuleDomain(
            title=updates.get("title"),
            position=updates.get("position"),
        )
        updated_domain = module_service.update_module(module_id=instance.id, update_data=update_domain)
        if not updated_domain:
            return Response({"detail": "Cannot update module"}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ModuleSerializer.from_domain(updated_domain))


class ModuleReorderView(APIView):
    """
    POST /api/courses/{course_id}/modules/reorder/
    body: {"order_map": {"<module_id>": <pos>, ...}}
    """
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]

    def post(self, request, course_id: str):
        course = get_object_or_404(models.Course, id=course_id)
        require_course_manager(request.user, course)
        order_map = request.data.get("order_map")
        if not isinstance(order_map, dict):
            return Response({"detail": "order_map must be object"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            module_service.reorder_modules(course_id=course_id, reorder_data={"order_map": order_map})
            return Response({"status": "ok"})
        except Exception as ex:
            return Response({"detail": str(ex)}, status=status.HTTP_400_BAD_REQUEST)
