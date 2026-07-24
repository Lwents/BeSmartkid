from django.contrib.auth import authenticate
from django.shortcuts import get_object_or_404
from rest_framework import status, generics, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authtoken.models import Token

from custom_account.models import UserModel, Profile, ParentalConsent
from custom_account.domains.parental_consent_domain import ParentalConsentDomain
from custom_account.serializers import (
    UserSerializer,
    RegisterSerializer,
    ChangePasswordSerializer,
    ResetPasswordSerializer,
    ProfileSerializer,
    ParentalConsentSerializer,
)
from custom_account.services import user_service, parental_consent_service



class ParentalConsentCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        parent_id = request.user.id
        data = request.data

        saved = parental_consent_service.grant_consent(parent_id=parent_id, child_id=data["child_id"], data=data)
        return Response(
            ParentalConsentSerializer.from_domain(saved),
            status=status.HTTP_201_CREATED,
        )


class ParentalConsentRevokeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        parent_id = request.user.id
        child_id = request.data.get("child_id")
        ok = parental_consent_service.revoke_consent(parent_id=parent_id, child_id=child_id)
        if not ok:
            return Response({"detail": "Consent not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ParentalConsentListView(generics.ListAPIView):
    serializer_class = ParentalConsentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # list consents given by current user (parent)
        return ParentalConsent.objects.filter(parent_id=self.request.user.id, revoked_at__isnull=True)