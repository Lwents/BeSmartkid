from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from school.serializers import EnrollmentSerializer
from school.services import enrollment_service


class EnrollmentListCreateView(APIView):
    """POST: enroll student, GET: list enrollments"""

    def get(self, request, classroom_id: str):
        enrollments = enrollment_service.list_enrollments(classroom_id)
        data = [EnrollmentSerializer.from_domain(e) for e in enrollments]
        return Response(data)

    def post(self, request, classroom_id: str):
        serializer = EnrollmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        domain = serializer.to_domain(classroom_id=classroom_id)
        enrollment = enrollment_service.enroll_student(domain)
        return Response(EnrollmentSerializer.from_domain(enrollment), status=status.HTTP_201_CREATED)


class EnrollmentDetailView(APIView):
    """DELETE: drop enrollment"""

    def delete(self, request, pk: str):
        enrollment_service.drop_enrollment(pk)
        return Response(status=status.HTTP_204_NO_CONTENT)
