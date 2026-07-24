import logging
from typing import List
from rest_framework.exceptions import ValidationError

from custom_account.domains.profile_domain import ProfileDomain
from custom_account.models import Profile , UserModel



logger = logging.getLogger(__name__)
def default_profile_metadata() -> dict:
    return {
        "email_updates": True,
        "email_notifications_enabled": True,
    }

def create_default_profile(user_id: int):
    """
    Service-layer method to create a default profile for a user.
    Contains business logic for *if* a profile can be created.
    """
    # Fetch the user from the repository
    try:
        user_to_link = UserModel.objects.get(id=user_id)
    except UserModel.DoesNotExist:
        raise ValidationError("User not found.")

    # Check if a profile already exists for this user
    if Profile.objects.filter(user=user_to_link).exists():
        raise ValidationError("Profile already exists for this user.")
        
    # Create the default object (repository operation)
    try:
        new_profile = Profile.objects.create(
            user=user_to_link,
            metadata=default_profile_metadata(),
        )
        return new_profile
    except Exception as e:
        logger.error(f"Error creating default profile in service: {e}", exc_info=True)
        raise ValidationError(f"Could not create profile: {e}")


def create_profile(domain: ProfileDomain) -> ProfileDomain:
    metadata = domain.metadata or {}
    metadata.setdefault("email_updates", True)
    metadata.setdefault("email_notifications_enabled", True)
    profile = Profile.objects.create(
        user_id=domain.user_id,
        display_name=domain.display_name,
        avatar_url=domain.avatar_url,
        dob=domain.dob,
        gender=domain.gender,
        language=domain.language,
        metadata=metadata,
    )
    return ProfileDomain.from_model(profile)


def update_profile(user_id: int, updates: dict) -> ProfileDomain:
    """Update profile fields via domain validation."""
    profile = Profile.objects.get(user_id=user_id)
    domain = ProfileDomain.from_model(profile)

    for field, value in updates.items():
        setattr(domain, field, value)

    domain.validate()
    for field, value in domain.to_dict().items():
        setattr(profile, field, value)
    profile.save()

    return ProfileDomain.from_model(profile)


def get_profile_by_user(user_id: int) -> ProfileDomain:
    profile = Profile.objects.get(user_id=user_id)
    return ProfileDomain.from_model(profile)


def list_all_profiles() -> List[ProfileDomain]:
    """
    Gets all profiles as a list of ProfileDomain entities.

    This follows the service layer pattern where the service
    interacts with the Model but returns Domain Entities.
    """
    profile_models = Profile.objects.select_related("user").all().order_by('user_id')
    
    # Convert models to domain entities.
    profile_domains = [ProfileDomain.from_model(profile) for profile in profile_models]
    
    # Return the list of domain entities
    return profile_domains


def delete_profile(user_id: int):
    """
    Service-layer method to delete a profile.
    Contains business logic for *if* a profile can be deleted.
    """
    # Fetch the domain object from the repository
    try:
        profile_to_delete = Profile.objects.get(user_id=user_id)
    except Profile.DoesNotExist:
        # Service layer should raise a domain/validation error, not Http404
        raise ValidationError("Profile not found.")
    
    profile_to_delete.delete()
