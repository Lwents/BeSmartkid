import logging
from django.http import Http404
from rest_framework import permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import ValidationError

from custom_account.models import UserModel, Profile
from custom_account.domains.profile_domain import ProfileDomain
from custom_account.api.mixins import RoleBasedOutputMixin
from custom_account.api.dtos.profile_dto import ProfilePublicOutput, ProfileAdminOutput, ProfileUpdateInput
from custom_account.serializers import ProfileSerializer, ProfileUpdateRequestSerializer
from django.utils import timezone
from custom_account.services import profile_service



# ---------- Profile endpoints ----------
def build_profile_payload(user, profile):
    metadata = profile.metadata or {}
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "phone": user.phone,
        "role": user.role,
        "full_name": profile.display_name or user.username,
        "avatar_url": profile.avatar_url,
        "dob": profile.dob,
        "gender": profile.gender,
        "class_name": getattr(profile, "class_name", None) or metadata.get("class_name", ""),
        "email_updates": metadata.get("email_updates", False),
        "address": metadata.get("address", ""),
        "city": metadata.get("city", ""),
        "district": metadata.get("district", ""),
        "ward": metadata.get("ward", ""),
        "parent_name": metadata.get("parent_name", ""),
        "parent_phone": metadata.get("parent_phone", ""),
        "parent_email": metadata.get("parent_email", ""),
        "parent_relation": metadata.get("parent_relation", ""),
        "parent_address": metadata.get("parent_address", ""),
        "title": metadata.get("title", ""),
        "bio": metadata.get("bio", ""),
        "created_on": user.created_on,
        "updated_on": profile.metadata.get("updated_on") or profile.user.updated_on,
    }


class UserProfileView(RoleBasedOutputMixin, APIView):
    """
    GET /api/account/profile/  -> get current user's profile
    PATCH /api/account/profile/ -> update current user's profile
    """
    permission_classes = [permissions.IsAuthenticated]

    output_dto_public = ProfilePublicOutput
    output_dto_admin = ProfileAdminOutput

    def get(self, request):
        """
        Handle GET requests to retrieve the user's profile.
        """
        user = request.user
        profile, _ = Profile.objects.get_or_create(
            user=user,
            defaults={
                "language": "vietnamese",
                "metadata": profile_service.default_profile_metadata(),
            },
        )
        return Response(build_profile_payload(user, profile), status=status.HTTP_200_OK)

    def patch(self, request):
        """
        Handle PATCH requests to update the user's profile.
        """
        if "role" in request.data or "is_staff" in request.data or "is_superuser" in request.data:
            raise ValidationError({
                'role': 'Bạn không thể tự thay đổi quyền của tài khoản.',
            })

        # Use a dedicated serializer *only* for validation
        serializer = ProfileUpdateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = request.user
        profile, _ = Profile.objects.get_or_create(
            user=user,
            defaults={
                "language": "vietnamese",
                "metadata": profile_service.default_profile_metadata(),
            },
        )
        metadata = profile.metadata or {}

        user_updated = False
        if "username" in data and data["username"]:
            user.username = data["username"]
            user_updated = True
        if "email" in data and data["email"]:
            incoming_email = data["email"].strip().lower()
            if UserModel.objects.filter(email__iexact=incoming_email).exclude(pk=user.pk).exists():
                raise ValidationError({'email': 'Email này đã được sử dụng bởi tài khoản khác.'})
            user.email = incoming_email
            user_updated = True
        if "phone" in data:
            incoming_phone = (data.get("phone") or "").strip()
            if incoming_phone and UserModel.objects.filter(phone__iexact=incoming_phone).exclude(pk=user.pk).exists():
                raise ValidationError({'phone': 'Số điện thoại này đã được sử dụng bởi tài khoản khác.'})
            user.phone = incoming_phone or ''
            user_updated = True
        if user_updated:
            user.save()

        if "full_name" in data:
            profile.display_name = data.get("full_name") or profile.display_name
        if "avatar_url" in data:
            profile.avatar_url = data.get("avatar_url") or profile.avatar_url
        if "dob" in data:
            profile.dob = data.get("dob")
        if "gender" in data:
            profile.gender = data.get("gender")
        if "class_name" in data:
            if hasattr(profile, "class_name"):
                profile.class_name = data.get("class_name") or profile.class_name
            else:
                metadata["class_name"] = data.get("class_name") or metadata.get("class_name")
        for key in ("address", "city", "district", "ward", "parent_name", "parent_phone", "parent_email", "parent_relation", "parent_address", "title", "bio", "class_name"):
            if key in data:
                metadata[key] = data[key]
        if "email_updates" in data:
            metadata["email_updates"] = data["email_updates"]
            metadata["email_notifications_enabled"] = data["email_updates"]

        metadata["updated_on"] = timezone.now().isoformat()
        profile.metadata = metadata
        profile.save()

        return Response(build_profile_payload(user, profile), status=status.HTTP_200_OK)
    

# ---- Admin ----
class AdminProfileListView(APIView):
    """
    GET /api/account/admin/profiles/ -> list all profiles (admin only)
    """
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.profile_service = profile_service 

    def get(self, request):
        try:
            # Service returns a list of DOMAIN ENTITIES
            profile_domains: list[ProfileDomain] = self.profile_service.list_all_profiles()
            
            # 2. Converts Domain -> DTO (using Pydantic)
            output_dtos = [
                ProfileAdminOutput.model_validate(domain) for domain in profile_domains
            ]
            
            # Serialize the list of DTOs into JSON
            json_data = [dto.model_dump() for dto in output_dtos]
            
            # Return the JSON list
            return Response(json_data, status=status.HTTP_200_OK)
        
        except Exception as e:
            return Response(
                {"detail": f"An error occurred: {str(e)}"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

logger = logging.getLogger(__name__)
class AdminProfileDetailView(RoleBasedOutputMixin, APIView):
    """
    POST   /api/account/profiles/{user_id}/ -> Create a default profile for this user (admin only)
    GET    /api/account/profiles/{user_id}/ -> Retrieve any user's profile (admin only)
    PATCH  /api/account/profiles/{user_id}/ -> Partially update any user's profile (admin only)
    DELETE /api/account/profiles/{user_id}/ -> Delete any user's profile (admin only)
    """
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    output_dto_public = ProfilePublicOutput
    output_dto_admin = ProfileAdminOutput

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.profile_service = profile_service  

    def get_object(self, user_id):
        """
        Helper method to get the *profile model* from the DB
        based on the user_id in the URL.
        """
        try:
            user = UserModel.objects.get(pk=user_id)
            return Profile.objects.get(user=user)
        except (UserModel.DoesNotExist, Profile.DoesNotExist):
            raise Http404

    def post(self, request, user_id, *args, **kwargs):
        """
        Handles POST requests to create a default profile for the user.
        This follows the DDD "Command" flow and takes no input body.
        """
        try:
            # Delegate to application service
            # The user_id comes directly from the URL
            created_domain = self.profile_service.create_default_profile(user_id=user_id)
            
            # Return the new Domain Entity for the mixin to process
            return Response(
                {"instance": created_domain}, 
                status=status.HTTP_201_CREATED
            )
        
        except ValidationError as e: # Or a specific DomainError
            # e.g., "User not found" or "Profile already exists"
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Unexpected error in AdminProfileDetailView POST: {e}", exc_info=True)
            return Response({"detail": "An unexpected error occurred."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def get(self, request, user_id, *args, **kwargs):
        """
        Handles GET requests to retrieve a single user's profile.
        """
        instance = self.get_object(user_id)
        
        # The 'RoleBasedOutputMixin' will intercept the raw model 
        # and convert it to the correct DTO (ProfileAdminOutput).
        return Response({"instance": instance})

    def patch(self, request, user_id, *args, **kwargs):
        """
        Handles PATCH requests to update a single user's profile.
        This follows the DDD "Command" flow.
        """
        instance = self.get_object(user_id)

        # Validate input using the serializer
        serializer = ProfileSerializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data
        
        # Create Input DTO
        profile_update_dto = ProfileUpdateInput(**validated_data)
        
        # Exclude 'None' values (or unset)
        updates_payload = profile_update_dto.model_dump(exclude_unset=True)
        
        if not updates_payload:
            # Nothing to update, just return the current state
            return Response({"instance": instance}, status=status.HTTP_200_OK)

        try:
            # Delegate to application service
            updated_domain = self.profile_service.update_profile(
                user_id=instance.user_id, 
                updates=updates_payload
            )
            
            # Return the Domain Entity for the mixin to process
            return Response({"instance": updated_domain}, status=status.HTTP_200_OK)
        
        except ValidationError as e: # Or a specific DomainError
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Unexpected error in AdminProfileDetailView: {e}", exc_info=True)
            return Response({"detail": "An unexpected error occurred."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
    def delete(self, request, user_id, *args, **kwargs):
        """
        Handles DELETE requests to remove a single user's profile.
        """
        # Get the object. This will raise Http404 if not found.
        instance = self.get_object(user_id)
        
        try:
            # Delegate the deletion logic to the application service
            self.profile_service.delete_profile(user_id=instance.user_id)
            
            return Response(status=status.HTTP_204_NO_CONTENT)

        except ValidationError as e: # Or a specific DomainError
            # e.g., "Cannot delete profile with active subscription"
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Unexpected error in AdminProfileDetailView delete: {e}", exc_info=True)
            return Response({"detail": "An unexpected error occurred."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    
