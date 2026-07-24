from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError

from student_api.permissions import IsStudent
from custom_account.models import UserModel


class StudentProfileView(APIView):
    """
    GET /api/student/account/profile/
    PUT /api/student/account/profile/
    Returns or updates student profile
    """
    permission_classes = [IsAuthenticated, IsStudent]

    @staticmethod
    def _profile_data(user, profile):
        """Serialize safely because the custom user does not extend AbstractUser."""
        joined_at = getattr(user, 'date_joined', None) or getattr(user, 'created_on', None)
        metadata = profile.metadata if isinstance(profile.metadata, dict) else {}
        return {
            'id': str(user.id),
            'username': getattr(user, 'username', '') or '',
            'email': getattr(user, 'email', '') or '',
            'firstName': getattr(user, 'first_name', '') or '',
            'lastName': getattr(user, 'last_name', '') or '',
            'fullName': user.get_full_name() or getattr(user, 'username', ''),
            'phone': getattr(user, 'phone', '') or '',
            'avatar': getattr(user, 'avatar', None),
            'class_name': getattr(profile, 'class_name', None) or metadata.get('class_name'),
            'role': getattr(user, 'role', 'student'),
            'dateJoined': joined_at.isoformat() if joined_at else None,
        }

    def get(self, request):
        """Get student profile"""
        user = request.user
        from custom_account.models import Profile
        profile, _ = Profile.objects.get_or_create(user=user, defaults={"language": "vietnamese"})
        
        return Response(self._profile_data(user, profile), status=status.HTTP_200_OK)

    def put(self, request):
        """Update student profile"""
        user = request.user
        from custom_account.models import Profile
        profile, _ = Profile.objects.get_or_create(user=user, defaults={"language": "vietnamese"})
        
        # Update allowed fields
        if 'firstName' in request.data and hasattr(user, 'first_name'):
            user.first_name = request.data['firstName']
        if 'lastName' in request.data and hasattr(user, 'last_name'):
            user.last_name = request.data['lastName']
        if ('firstName' in request.data or 'lastName' in request.data) \
                and not hasattr(user, 'first_name'):
            first_name = str(request.data.get('firstName', '') or '').strip()
            last_name = str(request.data.get('lastName', '') or '').strip()
            display_name = f"{first_name} {last_name}".strip()
            if display_name:
                profile.display_name = display_name
        if 'email' in request.data:
            user.email = request.data['email']
        if 'phone' in request.data:
            setattr(user, 'phone', request.data['phone'])
        if 'class_name' in request.data:
            if hasattr(profile, 'class_name'):
                profile.class_name = request.data.get('class_name') or profile.class_name
            else:
                meta = profile.metadata or {}
                meta['class_name'] = request.data.get('class_name') or meta.get('class_name')
                profile.metadata = meta
        
        user.save()
        profile.save()
        
        return Response(self._profile_data(user, profile), status=status.HTTP_200_OK)


class StudentChangePasswordView(APIView):
    """
    POST /api/student/account/change-password/
    Changes student password
    """
    permission_classes = [IsAuthenticated, IsStudent]

    def post(self, request):
        """Change password"""
        user = request.user
        
        old_password = request.data.get('oldPassword')
        new_password = request.data.get('newPassword')
        
        if not old_password or not new_password:
            return Response(
                {'detail': 'oldPassword and newPassword are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check old password
        if not user.check_password(old_password):
            return Response(
                {'detail': 'Incorrect old password'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate new password
        try:
            validate_password(new_password, user)
        except DjangoValidationError as e:
            return Response(
                {'detail': '; '.join(e.messages)},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Set new password
        user.set_password(new_password)
        user.save()
        
        # Update session to prevent logout
        update_session_auth_hash(request, user)
        
        return Response(
            {'detail': 'Password changed successfully'},
            status=status.HTTP_200_OK
        )


class StudentParentViewView(APIView):
    """
    GET /api/student/account/parent/
    PUT /api/student/account/parent/
    Returns or updates parent information for student
    """
    permission_classes = [IsAuthenticated, IsStudent]

    def get(self, request):
        """Get parent information"""
        user = request.user
        from custom_account.models import Profile
        profile, _ = Profile.objects.get_or_create(user=user, defaults={"language": "vietnamese"})
        metadata = profile.metadata if isinstance(profile.metadata, dict) else {}
        parent_data = {
            'name': metadata.get('parent_name', ''),
            'email': metadata.get('parent_email', ''),
            'phone': metadata.get('parent_phone', ''),
            'relationship': metadata.get('parent_relation', ''),
        }
        
        return Response(parent_data, status=status.HTTP_200_OK)

    def put(self, request):
        """Update parent information"""
        user = request.user
        from custom_account.models import Profile
        profile, _ = Profile.objects.get_or_create(user=user, defaults={"language": "vietnamese"})
        metadata = dict(profile.metadata) if isinstance(profile.metadata, dict) else {}
        field_map = {
            'name': 'parent_name',
            'email': 'parent_email',
            'phone': 'parent_phone',
            'relationship': 'parent_relation',
        }
        for request_key, metadata_key in field_map.items():
            if request_key in request.data:
                metadata[metadata_key] = str(request.data.get(request_key) or '').strip()
        profile.metadata = metadata
        profile.save(update_fields=['metadata'])
        parent_data = {
            'name': metadata.get('parent_name', ''),
            'email': metadata.get('parent_email', ''),
            'phone': metadata.get('parent_phone', ''),
            'relationship': metadata.get('parent_relation', ''),
        }
        
        return Response(parent_data, status=status.HTTP_200_OK)
