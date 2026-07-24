from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from school.serializers import SchoolSerializer
from school.services import school_service


class SchoolListCreateView(APIView):
    """POST: create school, GET: list schools"""

    def get(self, request):
        schools = school_service.list_schools()
        data = [SchoolSerializer.from_domain(s) for s in schools]
        return Response(data)

    def post(self, request):
        serializer = SchoolSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        domain = serializer.to_domain()
        school = school_service.create_school(domain)
        return Response(SchoolSerializer.from_domain(school), status=status.HTTP_201_CREATED)


class SchoolDetailView(APIView):
    """GET, PUT, DELETE on a school"""

    def get(self, request, pk: str):
        school = school_service.get_school(pk)
        return Response(SchoolSerializer.from_domain(school))

    def put(self, request, pk: str):
        serializer = SchoolSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        domain = serializer.to_domain(id=pk)
        school = school_service.update_school(domain)
        return Response(SchoolSerializer.from_domain(school))

    def delete(self, request, pk: str):
        school_service.archive_school(pk)
        return Response(status=status.HTTP_204_NO_CONTENT)
