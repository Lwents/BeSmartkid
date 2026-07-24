import logging
from typing import Optional, Any, Dict, List
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import transaction

from custom_account.domains.user_domain import UserDomain
from custom_account.domains.reset_password_domain import ResetPasswordDomain
from custom_account.models import UserModel
from custom_account.models import Profile
from custom_account.services.exceptions import DomainError, UserNotFoundError, IncorrectPasswordError
from custom_account.services.profile_service import default_profile_metadata

try:
    from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
except (ImportError, RuntimeError):  # blacklist app might be disabled
    OutstandingToken = None  # type: ignore
    BlacklistedToken = None  # type: ignore

logger = logging.getLogger(__name__)

def register_user(data: dict) -> UserDomain:
    """Register a new user and its profile (aggregate root = User)."""

    # enforce business invariants (uniqueness)
    if UserModel.objects.filter(username__iexact=data['username']).exists():
        raise DomainError("Username already taken")
    if UserModel.objects.filter(email__iexact=data['email']).exists():
        raise DomainError("Email already taken")
    phone = data.get('phone')
    if phone and UserModel.objects.filter(phone__iexact=phone).exists():
        raise DomainError("Phone already taken")

    user_domain = UserDomain(username=data['username'],
                             email=data['email'],
                             raw_password=data['password'],
                             role=data['role'],
                             phone=phone)

    user = user_domain.to_model()
    user.save()

    # create profile aggregate part
    user_domain.id = user.id
    profile_domain = user_domain.create_profile()
    profile_data = data.get('profile', {})
    metadata = profile_data.get('metadata') or {}
    defaults = default_profile_metadata()
    metadata.setdefault('email_updates', defaults['email_updates'])
    metadata.setdefault('email_notifications_enabled', defaults['email_notifications_enabled'])
    profile_data['metadata'] = metadata
    Profile.objects.create(user=user, **profile_data)
    return UserDomain.from_model(user)


def change_password(user_id: int, old_password: str, new_password: str) -> bool:
    """Change password for a given user."""
    try:
        user = UserModel.objects.get(pk=user_id)
    except ObjectDoesNotExist:
        raise UserNotFoundError("User not found")

    if not user.check_password(old_password):
        raise IncorrectPasswordError("Old password is incorrect")

    user.set_password(new_password)
    user.save()
    return True


def admin_set_password(user_id: int, new_password: str):
    """
    Finds a user by ID and sets their password directly.
    Does not check the old password.
    Raises UserNotFoundError if the user doesn't exist.
    """
    try:
        user = UserModel.objects.get(id=user_id)
    except UserModel.DoesNotExist:
        raise UserNotFoundError("User not found.")
    
    # Use Django's set_password to handle hashing
    user.set_password(new_password)
    user.save(update_fields=["password"])


def reset_password(domain: ResetPasswordDomain) -> bool:
    """Reset password using reset token (stub)."""
    try:
        user = UserModel.objects.get(email=domain.email)
    except ObjectDoesNotExist:
        raise ValueError("User not found")

    # TODO: verify reset token properly
    if not domain.reset_token:
        raise ValueError("Invalid reset token")

    user.set_password(domain.new_password)
    user.save()
    return True


def get_user_by_id(user_id: int) -> UserDomain:
    user = UserModel.objects.get(pk=user_id)
    return UserDomain.from_model(user)


def get_user_by_username(username: str) -> UserDomain:
    user = UserModel.objects.get(username=username)
    return UserDomain.from_model(user)

def get_user_by_email(email: str) -> UserDomain:
    User = UserModel.objects.get(email=email)
    return UserDomain.from_model(User)


def update_user(user_id: int, updates: Dict[str, Any]) -> UserDomain:
    """Update user from domain object."""
    user = UserModel.objects.get(pk=user_id)
    domain = UserDomain.from_model(user)

    # Áp dụng updates và validate
    domain.apply_updates(updates)

    # Lưu vào database
    for key, value in updates.items():
        if hasattr(user, key):
            setattr(user, key, value)
    user.save()
    return domain


def deactivate_user(user_id: int) -> bool:
    try:
        user = UserModel.objects.get(id=user_id)
        user.is_active = False
        user.save()
        return True
    except UserModel.DoesNotExist:
        return False
    

def reactivate_user(user_id: int) -> Optional[UserDomain]:
    try:
        user = UserModel.objects.get(id=user_id)
        user.is_active = True
        user.save()
        return UserDomain.from_model(user)
    except UserModel.DoesNotExist:
        return None
    
def delete_user(user_id):
    """
    Service-layer method to delete a user.
    Contains business logic for *if* a user can be deleted.
    """
    # Fetch the domain object from the repository
    try:
        user_to_delete = UserModel.objects.get(id=user_id)
    except UserModel.DoesNotExist:
        raise ValidationError("User not found.")

    with transaction.atomic():
        if OutstandingToken:
            try:
                token_qs = OutstandingToken.objects.filter(user=user_to_delete)
                if token_qs.exists():
                    token_ids = list(token_qs.values_list('id', flat=True))
                    if BlacklistedToken and token_ids:
                        BlacklistedToken.objects.filter(token_id__in=token_ids).delete()
                    token_qs.delete()
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Failed to cleanup JWT tokens for user %s: %s", user_id, exc)

        user_to_delete.delete()
    

def list_all_users_for_admin(
    role: Optional[str] = None, 
    page: int = 1, 
    page_size: int = 50,
    q: Optional[str] = None,
    status: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    sort_by: str = 'created_on',
    sort_dir: str = 'descending'
) -> Dict[str, Any]:
    """
    Gets all users as a list of UserDomain entities with pagination and filtering.

    This follows the style of 'register_user', where the service
    layer interacts with the Model but returns Domain Entities.
    
    Filters:
    - q: Search by username, email (case-insensitive, partial match)
    - role: Filter by role (admin, instructor, student)
    - status: Filter by status (active, locked, banned)
    - from_date/to_date: Filter by created_on date range
    - sort_by/sort_dir: Sorting
    """
    from django.db.models import Q
    from django.utils.dateparse import parse_date
    
    # Limit page_size to prevent excessive data load (searchUS_25, searchUS_29)
    page_size = min(page_size, 100)
    
    # Use select_related/only to optimize query (searchUS_25)
    queryset = UserModel.objects.only(
        'id', 'username', 'email', 'role', 'is_staff', 'is_active', 
        'phone', 'created_on', 'updated_on', 'last_login'
    )
    queryset = queryset.exclude(Q(is_staff=True) | Q(role='admin'))
    
    # Search by q (username, email)
    if q:
        q = q.strip()
        queryset = queryset.filter(
            Q(username__icontains=q) | 
            Q(email__icontains=q)
        )
    
    # Filter by role if provided
    if role:
        # Map frontend role names to backend role names
        # Database stores: 'student', 'instructor', 'admin'
        role_mapping = {
            'instructor': 'instructor',
            'teacher': 'instructor',
            'student': 'student',
            'admin': 'admin'
        }
        backend_role = role_mapping.get(role, role)
        if backend_role == 'admin':
            queryset = queryset.filter(is_staff=True)
        else:
            queryset = queryset.filter(role=backend_role, is_staff=False)
    
    # Filter by status
    if status:
        if status == 'active':
            queryset = queryset.filter(is_active=True)
        elif status == 'locked':
            queryset = queryset.filter(is_active=False)
        elif status == 'banned':
            # Assuming banned users have is_active=False (or add a separate field)
            queryset = queryset.filter(is_active=False)
    
    # Filter by date range
    if from_date:
        parsed_from = parse_date(from_date)
        if parsed_from:
            queryset = queryset.filter(created_on__date__gte=parsed_from)
    if to_date:
        parsed_to = parse_date(to_date)
        if parsed_to:
            queryset = queryset.filter(created_on__date__lte=parsed_to)
    
    # Sorting
    sort_field_mapping = {
        'createdAt': 'created_on',
        'created_on': 'created_on',
        'lastLoginAt': 'last_login',
        'last_login': 'last_login',
        'username': 'username',
        'email': 'email',
    }
    sort_field = sort_field_mapping.get(sort_by, 'created_on')
    if sort_dir == 'descending':
        sort_field = f'-{sort_field}'
    queryset = queryset.order_by(sort_field)
    
    # Pagination
    total = queryset.count()
    start = (page - 1) * page_size
    end = start + page_size
    user_models = queryset[start:end]
    
    user_domains = [UserDomain.from_model(user) for user in user_models]
    
    return {
        'results': user_domains,
        'count': total,
        'page': page,
        'page_size': page_size,
        'total_pages': (total + page_size - 1) // page_size
    }

@transaction.atomic
def synchronize_roles() -> dict:
    """
    Finds and fixes role/is_staff mismatches in the database.
    
    - If is_staff=True, role MUST be 'admin'.
    - If is_staff=False, role CANNOT be 'admin'.
    """
    
    # Fix users who ARE staff but their role IS NOT 'admin' (e.g., is_staff=True, role='student')
    updated_to_admin_count = UserModel.objects.filter(is_staff=True
                                             ).exclude(role='admin'
                                             ).update(role='admin')

    # Fix users who ARE NOT staff but their role IS 'admin' (e.g., is_staff=False, role='admin')
    updated_to_student_count = UserModel.objects.filter(is_staff=False,role='admin'
                                               ).update(role='student')

    # Return a report of what was fixed
    return {
        "users_updated_to_admin": updated_to_admin_count,
        "users_updated_from_admin": updated_to_student_count,
        "detail": "Role synchronization complete."
    }


    
    
