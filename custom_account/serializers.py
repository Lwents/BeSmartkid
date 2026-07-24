import base64
import binascii
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.exceptions import AuthenticationFailed
from django.core.exceptions import ValidationError, ObjectDoesNotExist

from custom_account.models import UserModel, Profile, ParentalConsent
from custom_account.domains.user_domain import UserDomain
from custom_account.domains.profile_domain import ProfileDomain
from custom_account.domains.parental_consent_domain import ParentalConsentDomain
from custom_account.domains.change_password_domain import ChangePasswordDomain
from custom_account.domains.reset_password_domain import ResetPasswordDomain
from custom_account.services import auth_service, profile_service

"""Serializer for sending user data in responses."""
class UserSerializer(serializers.ModelSerializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=15, required=False)
    created_on = serializers.DateTimeField(read_only=True)
    # 🚨 notice: we don’t expose password in API responses

    class Meta:
        model = UserModel
        fields = [
            "id", "username", "email", "is_active",
            "phone", "created_on", "role"
        ]
        read_only_fields = ["id", "created_on"]

    def get_fields(self):
        """Dynamically make some fields read-only depending on the user."""
        fields = super().get_fields()

        request = self.context.get("request", None)
        if request and not request.user.is_staff:  # Non-admin user
            # Make restricted fields read-only
            fields["role"].read_only = True
            fields["is_active"].read_only = True

        return fields
    
    def to_domain(self) -> UserDomain:
        """Convert serializer data -> UserDomain."""
        return UserDomain.from_dict(self.validated_data)

    @staticmethod
    def from_domain(domain: UserDomain) -> dict:
        """Convert UserDomain -> dict (API response)."""
        return domain.to_dict()
    
    def to_representation(self, instance):
        # Nếu instance là UserDomain, convert sang dict
        if isinstance(instance, UserDomain):
            return {
                'id': instance.id,
                'username': instance.username,
                'email': instance.email,
                'role': instance.role,
                'created_on': instance.created_on,
                'phone': instance.phone,
            }
        return super().to_representation(instance)


class ProfileSerializer(serializers.ModelSerializer):
    """Serializer for Profile <-> ProfileDomain mapping."""

    class Meta:
        model = Profile
        fields = [
            "user_id", "display_name", "avatar_url",
            "dob", "gender", "language", "metadata"
        ]
        read_only_fields = ["user_id"]

    def to_domain(self) -> ProfileDomain:
        """Convert serializer data to domain object."""
        data = dict(self.validated_data)

        # inject user_id from context or instance
        if self.instance:
            data["user_id"] = self.instance.user_id
        else:
            # trường hợp create profile
            user = self.context.get("user")
            if not user:
                raise ValueError("Missing user in serializer context")
            data["user_id"] = user.id

        domain = ProfileDomain.from_dict(data)
        domain.validate()
        return domain

    @staticmethod
    def from_domain(domain: ProfileDomain) -> dict:
        return domain.to_dict()


class ParentalConsentSerializer(serializers.ModelSerializer):
    """Serializer for ParentalConsent <-> ParentalConsentDomain mapping."""

    class Meta:
        model = ParentalConsent
        fields = [
            "id", "parent", "child", "consented_at",
            "scopes", "revoked_at", "metadata"
        ]
        read_only_fields = ["id", "consented_at"]

    def to_domain(self) -> ParentalConsentDomain:
        return ParentalConsentDomain.from_dict(self.validated_data)

    @staticmethod
    def from_domain(domain: ParentalConsentDomain) -> dict:
        return domain.to_dict()



"""Serializer for user registration requests (input only)."""
class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=6)
    role = serializers.ChoiceField(choices=["student", "instructor", "admin"], default="student")
    phone = serializers.CharField(max_length=15, required=False)

    def to_domain(self):
        """Convert validated data into a UserDomain object"""
        return UserDomain(**self.validated_data)
    

class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def to_domain(self, user_id: int) -> ChangePasswordDomain:
        return ChangePasswordDomain(
            user_id=user_id,
            old_password=self.validated_data["old_password"],
            new_password=self.validated_data["new_password"]
        )
    

class SetPasswordSerializer(serializers.Serializer):
    new_password = serializers.CharField(write_only=True, required=True)


class PasswordChangeOTPVerifySerializer(serializers.Serializer):
    otp = serializers.CharField(max_length=6)
    new_password = serializers.CharField(write_only=True, min_length=6)
    

class ProfileUpdateRequestSerializer(serializers.Serializer):
    username = serializers.CharField(required=False, allow_blank=True, max_length=150)
    full_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    phone = serializers.CharField(required=False, allow_blank=True, max_length=20)
    email = serializers.EmailField(required=False, allow_blank=True)
    avatar_url = serializers.CharField(required=False, allow_blank=True)
    dob = serializers.DateField(required=False)
    gender = serializers.ChoiceField(choices=["male", "female", "other"], required=False)
    class_name = serializers.CharField(required=False, allow_blank=True, max_length=128)
    title = serializers.CharField(required=False, allow_blank=True, max_length=255)
    bio = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    email_updates = serializers.BooleanField(required=False)
    address = serializers.CharField(required=False, allow_blank=True, max_length=255)
    city = serializers.CharField(required=False, allow_blank=True, max_length=100)
    district = serializers.CharField(required=False, allow_blank=True, max_length=100)
    ward = serializers.CharField(required=False, allow_blank=True, max_length=100)
    parent_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    parent_phone = serializers.CharField(required=False, allow_blank=True, max_length=20)
    parent_email = serializers.EmailField(required=False, allow_blank=True)
    parent_relation = serializers.CharField(required=False, allow_blank=True, max_length=50)
    parent_address = serializers.CharField(required=False, allow_blank=True, max_length=255)

    def validate_avatar_url(self, value):
        if not value:
            return value
        if not isinstance(value, str):
            return value
        if value.startswith("data:") and "base64," in value:
            base64_data = value.split("base64,", 1)[1].strip()
            if not base64_data:
                return value
            padding = base64_data.count("=")
            size_bytes = (len(base64_data) * 3) // 4 - padding
            if size_bytes > 5 * 1024 * 1024:
                raise serializers.ValidationError("Dung lượng ảnh đại diện vượt quá 5MB.")
            try:
                base64.b64decode(base64_data, validate=True)
            except (binascii.Error, ValueError):
                raise serializers.ValidationError("Ảnh đại diện không hợp lệ.")
        return value


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()
    reset_token = serializers.CharField()
    new_password = serializers.CharField(write_only=True)

    def to_domain(self) -> ResetPasswordDomain:
        return ResetPasswordDomain.from_dict(self.validated_data)

    
class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    username_field = 'username_or_email'
    username_or_email = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        username_or_email = attrs.get("username_or_email")
        password = attrs.get("password")

        # Authenticate using custom service
        try:
            user = auth_service.authenticate_user(username_or_email, password)
        except ValidationError as e:
            # Raise AuthenticationFailed for invalid credentials to return 401
            raise AuthenticationFailed("No active account found with the given credentials", code="authentication")

        # Set user to bypass parent authentication
        self.user = user

        # Get profile
        try:
            profile = profile_service.get_profile_by_user(user.id)
        except ObjectDoesNotExist:
            profile = profile_service.create_default_profile(user.id)

        # Generate tokens manually
        refresh = RefreshToken.for_user(user)
        data = {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user': {
                'username': user.username,
                'email': user.email,
                'role': "admin" if user.is_staff else user.role,
                'full_name': profile.display_name if profile.display_name else user.username,
            }
        }
        return data
    

class UserPublicOutputSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = UserModel
        fields = ['username', 'email', 'role', 'full_name']

    def get_role(self, user_obj):
        if user_obj.is_staff:
            return "admin"
        
        if hasattr(user_obj, 'role'):
            return user_obj.role
        return "student" 

    def get_full_name(self, user_obj):
        try:
            profile = user_obj.profile 
            if profile.display_name:
                return profile.display_name
            return user_obj.username
        except Exception:
            return user_obj.username
