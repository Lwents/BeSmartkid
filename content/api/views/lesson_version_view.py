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



class LessonVersionListCreateView(generics.ListCreateAPIView):
    """
    GET /api/lessons/{lesson_id}/versions/
    POST /api/lessons/{lesson_id}/versions/
    """
    serializer_class = LessonVersionSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        lesson_id = self.kwargs.get("lesson_id")
        return models.LessonVersion.objects.filter(lesson_id=lesson_id).order_by("-version")

    def create(self, request, lesson_id=None, *args, **kwargs):
        serializer = CreateLessonVersionInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cmd = serializer.to_domain(lesson_id=lesson_id)
        created_domain = LessonVersionService.create_version(cmd)
        return Response(LessonVersionSerializer.from_domain(created_domain), status=status.HTTP_201_CREATED)


class LessonVersionDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET /api/lesson-versions/{id}/
    PATCH /api/lesson-versions/{id}/
    DELETE /api/lesson-versions/{id}/
    """
    queryset = models.LessonVersion.objects.all()
    serializer_class = LessonVersionSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsOwnerOrAdmin]

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updates = serializer.validated_data
        updated_domain = lesson_version_service.update_version(version_id=instance.id, update_data=updates)
        if not updated_domain:
            return Response({"detail": "Cannot update version"}, status=status.HTTP_400_BAD_REQUEST)
        return Response(LessonVersionSerializer.from_domain(updated_domain))


class LessonVersionPublishView(APIView):
    """
    POST /api/lessons/{lesson_id}/versions/publish/
    body: {"version": <int>, "publish_comment": "..."}
    """
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]

    def post(self, request, lesson_id: str):
        serializer = PublishLessonVersionInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cmd = serializer.to_domain(lesson_id=lesson_id)
        try:
            published_domain = LessonVersionService.change_status(version_id=None, status_data={"lesson_id": cmd.lesson_id, "version": cmd.version, "status": "published"})
            # note: service API may differ; adapt as needed
            if not published_domain:
                return Response({"detail": "Could not publish"}, status=status.HTTP_400_BAD_REQUEST)
            return Response(LessonVersionSerializer.from_domain(published_domain))
        except Exception as ex:
            return Response({"detail": str(ex)}, status=status.HTTP_400_BAD_REQUEST)