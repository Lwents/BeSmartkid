from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from school.serializers import InvitationSerializer
from school.services import invitation_service


class InvitationListCreateView(APIView):
    """List or create invitations for a classroom"""

    def get(self, request, classroom_id: int):
        invitations = invitation_service.list_invitations(classroom_id)
        data = [InvitationSerializer.from_domain(i) for i in invitations]
        return Response(data)

    def post(self, request, classroom_id: int):
        serializer = InvitationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        domain = serializer.to_domain(classroom_id=classroom_id)
        invitation = invitation_service.create_invitation(domain)
        return Response(
            InvitationSerializer.from_domain(invitation),
            status=status.HTTP_201_CREATED
        )


class InvitationAcceptView(APIView):
    """Accept an invitation"""

    def post(self, request, invitation_id: int):
        invitation = invitation_service.accept_invitation(
            invitation_id, request.user.id
        )
        return Response(InvitationSerializer.from_domain(invitation))


class InvitationRevokeView(APIView):
    """Revoke an invitation"""

    def post(self, request, invitation_id: int):
        invitation_service.revoke_invitation(invitation_id)
        return Response(status=status.HTTP_204_NO_CONTENT)
