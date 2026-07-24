from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from school.serializers import MembershipSerializer
from school.services import membership_service


class MembershipListCreateView(APIView):
    """Manage memberships in a classroom"""

    def get(self, request, classroom_id: int):
        memberships = membership_service.list_members(classroom_id)
        data = [MembershipSerializer.from_domain(m) for m in memberships]
        return Response(data)

    def post(self, request, classroom_id: int):
        serializer = MembershipSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        domain = serializer.to_domain(classroom_id=classroom_id)
        membership = membership_service.add_member(domain)
        return Response(
            MembershipSerializer.from_domain(membership),
            status=status.HTTP_201_CREATED
        )


class MembershipDetailView(APIView):
    """Update or remove a membership"""

    def put(self, request, classroom_id: int, user_id: int):
        serializer = MembershipSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        domain = serializer.to_domain(
            classroom_id=classroom_id, user_id=user_id
        )
        membership = membership_service.update_membership(domain)
        return Response(MembershipSerializer.from_domain(membership))

    def delete(self, request, classroom_id: int, user_id: int):
        membership_service.remove_member(classroom_id, user_id)
        return Response(status=status.HTTP_204_NO_CONTENT)
