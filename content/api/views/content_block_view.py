from typing import Any, Dict
from django.db import transaction
from django.shortcuts import get_object_or_404

from rest_framework import generics, status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response

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

from custom_account.api.permissions import IsOwnerOrAdmin
from content.services.subject_service import SubjectService
from content.services.course_service import CourseService
from content.services.module_service import ModuleService
from content.services.lesson_service import LessonService
from content.services.lesson_version_service import LessonVersionService
from content.services.content_block_service import ContentBlockService
from content.services.exploration_service import (
    ExplorationService, ExplorationStateService, ExplorationTransitionService
)



class ContentBlockListCreateView(generics.ListCreateAPIView):
    """
    GET /api/lesson-versions/{lesson_version_id}/blocks/
    POST /api/lesson-versions/{lesson_version_id}/blocks/
    """
    serializer_class = ContentBlockSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        lv_id = self.kwargs.get("lesson_version_id")
        return models.ContentBlock.objects.filter(lesson_version_id=lv_id).order_by("position")

    def create(self, request, lesson_version_id=None, *args, **kwargs):
        serializer = AddContentBlockInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cmd = serializer.to_domain(lesson_version_id=lesson_version_id)
        created_domain = ContentBlockService.create_block(cmd)
        return Response(ContentBlockSerializer.from_domain(created_domain), status=status.HTTP_201_CREATED)


class ContentBlockDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET /api/content-blocks/{id}/
    PATCH /api/content-blocks/{id}/
    DELETE /api/content-blocks/{id}/
    """
    queryset = models.ContentBlock.objects.all()
    serializer_class = ContentBlockSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsOwnerOrAdmin]

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updates = serializer.validated_data
        updated_domain = content_block_service.update_block(block_id=instance.id, update_data=updates)
        if not updated_domain:
            return Response({"detail": "Cannot update content block"}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ContentBlockSerializer.from_domain(updated_domain))