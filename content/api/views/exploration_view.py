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



class ExplorationListCreateView(generics.ListCreateAPIView):
    """
    GET /api/explorations/
    POST /api/explorations/
    """
    serializer_class = ExplorationSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        return models.Exploration.objects.all()

    def create(self, request, *args, **kwargs):
        serializer = CreateExplorationInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cmd = serializer.to_domain()
        created_domain = ExplorationService.create_exploration(cmd)
        return Response(ExplorationSerializer.from_domain(created_domain), status=status.HTTP_201_CREATED)


class ExplorationDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET /api/explorations/{id}/
    PATCH /api/explorations/{id}/
    DELETE /api/explorations/{id}/
    """
    queryset = models.Exploration.objects.all()
    serializer_class = ExplorationSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsOwnerOrAdmin]

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updates = serializer.validated_data
        updated_domain = exploration_service.update_exploration(exploration_id=instance.id, update_data=updates)
        if not updated_domain:
            return Response({"detail": "Cannot update exploration"}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ExplorationSerializer.from_domain(updated_domain))


class ExplorationPublishView(APIView):
    """
    POST /api/explorations/{id}/publish/
    """
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]

    def post(self, request, exploration_id: str):
        publish_flag = request.data.get("published", True)
        try:
            updated = ExplorationService.publish_exploration(exploration_id=exploration_id, publish_data={"published": publish_flag})
            if not updated:
                return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
            return Response(ExplorationSerializer.from_domain(updated))
        except Exception as ex:
            return Response({"detail": str(ex)}, status=status.HTTP_400_BAD_REQUEST)


# ---------------------------
# Exploration State & Transition endpoints
# ---------------------------
class ExplorationStateListCreateView(generics.ListCreateAPIView):
    """
    GET /api/explorations/{exploration_id}/states/
    POST /api/explorations/{exploration_id}/states/
    """
    serializer_class = ExplorationStateSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        exploration_id = self.kwargs.get("exploration_id")
        return models.ExplorationState.objects.filter(exploration_id=exploration_id)

    def create(self, request, exploration_id=None, *args, **kwargs):
        serializer = AddExplorationStateInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cmd = serializer.to_domain(exploration_id=exploration_id)
        created_domain = ExplorationStateService.create_state(cmd)
        return Response(ExplorationStateSerializer.from_domain(created_domain), status=status.HTTP_201_CREATED)


class ExplorationStateDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = models.ExplorationState.objects.all()
    serializer_class = ExplorationStateSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsOwnerOrAdmin]

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updates = serializer.validated_data
        updated_domain = exploration_state_service.update_state(state_id=instance.id, update_data=updates)
        if not updated_domain:
            return Response({"detail": "Cannot update state"}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ExplorationStateSerializer.from_domain(updated_domain))


class ExplorationTransitionListCreateView(generics.ListCreateAPIView):
    """
    GET /api/explorations/{exploration_id}/transitions/
    POST /api/explorations/{exploration_id}/transitions/
    """
    serializer_class = ExplorationTransitionSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        exploration_id = self.kwargs.get("exploration_id")
        return models.ExplorationTransition.objects.filter(exploration_id=exploration_id)

    def create(self, request, exploration_id=None, *args, **kwargs):
        serializer = AddExplorationTransitionInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cmd = serializer.to_domain(exploration_id=exploration_id)
        created_domain = ExplorationTransitionService.create_transition(cmd)
        return Response(ExplorationTransitionSerializer.from_domain(created_domain), status=status.HTTP_201_CREATED)


class ExplorationTransitionDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = models.ExplorationTransition.objects.all()
    serializer_class = ExplorationTransitionSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsOwnerOrAdmin]

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updates = serializer.validated_data
        # service may implement update_transition
        updated_domain = exploration_transition_service.update_transition(transition_id=instance.id, update_data=updates)
        if not updated_domain:
            return Response({"detail": "Cannot update transition"}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ExplorationTransitionSerializer.from_domain(updated_domain))