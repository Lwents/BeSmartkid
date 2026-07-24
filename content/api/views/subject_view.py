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

from content.services.subject_service import SubjectService
from content.services.course_service import CourseService
from content.services.module_service import ModuleService
from content.services.lesson_service import LessonService
from content.services.lesson_version_service import LessonVersionService
from content.services.content_block_service import ContentBlockService
from content.services.exploration_service import (
    ExplorationService, ExplorationStateService, ExplorationTransitionService
)



class SubjectListCreateView(generics.ListCreateAPIView):
    """
    GET /api/subjects/         -> list subjects (public)
    POST /api/subjects/        -> create subject (auth required, e.g. staff/instructor)
    """
    queryset = models.Subject.objects.all()
    serializer_class = SubjectSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # convert to domain command
        domain_cmd = serializer.to_domain()
        created = subject_service.create_subject(domain_cmd)
        return Response(SubjectSerializer.from_domain(created), status=status.HTTP_201_CREATED)


class SubjectDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET /api/subjects/{id}/
    PATCH /api/subjects/{id}/   (staff/admin)
    DELETE /api/subjects/{id}/  (staff/admin)
    """
    queryset = models.Subject.objects.all()
    serializer_class = SubjectSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", True)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        updates = serializer.validated_data
        # delegate to service; service handles domain-level validation
        updated_domain = subject_service.update_subject(subject_id=instance.id, update_data=updates)
        if updated_domain is None:
            return Response({"detail": "Not found or cannot update"}, status=status.HTTP_400_BAD_REQUEST)
        return Response(SubjectSerializer.from_domain(updated_domain))