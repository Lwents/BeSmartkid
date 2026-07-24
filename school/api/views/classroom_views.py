from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from school.serializers import (
    ClassroomSerializer,
    ClassroomCreateSerializer,
    ClassroomUpdateSerializer,
)
from school.services.classroom_service import (
    list_classrooms,
    create_classroom,
    get_classroom,
    update_classroom,
    archive_classroom,
)


class ClassroomListCreateView(APIView):
    """GET: list classrooms, POST: create new classroom"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        classrooms = list_classrooms(user=request.user)
        data = [ClassroomSerializer.from_domain(c) for c in classrooms]
        return Response(data)

    def post(self, request):
        serializer = ClassroomCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        domain = serializer.to_domain()
        # Set created_by to current user if not set
        if not domain.created_by:
            domain.created_by = request.user.id
        classroom = create_classroom(domain)
        return Response(
            ClassroomSerializer.from_domain(classroom),
            status=status.HTTP_201_CREATED
        )


class ClassroomDetailView(APIView):
    """GET: retrieve classroom, PUT: update classroom, DELETE: archive"""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk: int):
        classroom = get_classroom(pk)
        return Response(ClassroomSerializer.from_domain(classroom))

    def put(self, request, pk: int):
        serializer = ClassroomUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        domain = serializer.to_domain(pk)
        classroom = update_classroom(domain)
        return Response(ClassroomSerializer.from_domain(classroom))

    def delete(self, request, pk: int):
        archive_classroom(pk)
        return Response(status=status.HTTP_204_NO_CONTENT)
