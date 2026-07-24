from typing import Optional, Callable, List
from django.db import transaction

from custom_account.models import UserModel
from school.models import ClassroomModel, MembershipModel, InvitationModel
from school.domains.membership_domain import MembershipDomain
from school.domains.invitation_domain import InvitationDomain
from school.services.exceptions import NotFoundError, PermissionDenied, ConflictError, InvalidOperation
from school.services.validators import ensure_is_admin_or_instructor


# --- Helpers ---
def create_membership(classroom_model: ClassroomModel, user: UserModel, role: str) -> MembershipDomain:
    if MembershipModel.objects.filter(
        classroom=classroom_model, student=user, is_active=True
    ).exists():
        raise ConflictError("User is already an active member of this classroom.")

    membership_model = MembershipModel.objects.create(
        classroom=classroom_model,
        student=user,
        role=role,
        is_active=True,
    )
    return MembershipDomain.from_model(membership_model)


def deactivate_membership(membership: MembershipModel, *, allow_self: bool = False, soft_delete: bool = True) -> None:
    """
    Internal helper to deactivate a membership with business rules:
    - Prevent removing last instructor.
    - Support soft/hard delete (default soft).
    """

    role = membership.role
    # 1. Check not removing the last instructor
    if role in ("instructor", "co-instructor"):
        total_instructors = MembershipModel.objects.filter(
            classroom_id=membership.classroom_id,
            role__iexact="instructor",
            is_active=True
        ).count()
        if total_instructors <= 1:
            raise InvalidOperation("Cannot remove the last instructor.")

    # 2. Deactivate membership
    if soft_delete:
        membership.is_active = False
        membership.save(update_fields=["is_active"])
    else:
        membership.delete()



# --- Services ---

# Student
@transaction.atomic
def join_classroom(student: UserModel, classroom_id: int, *, invite_code: str = None) -> MembershipDomain:
    """
    Student joins a classroom (via invite code or open join).
    """
    try:
        classroom_model = ClassroomModel.objects.select_for_update().get(id=classroom_id)
    except ClassroomModel.DoesNotExist:
        raise NotFoundError("Classroom not found.")

    if classroom_model.status != "active":
        raise InvalidOperation("Cannot join non-active classroom.")

    if invite_code:
        try:
            invitation_model = InvitationModel.objects.select_for_update().get(
                invite_code=invite_code, classroom=classroom_model
            )
        except InvitationModel.DoesNotExist:
            raise NotFoundError("Invitation not found.")

        invitation_domain = InvitationDomain.from_model(invitation_model)
        if not invitation_domain.is_valid():
            invitation_model.status = "expired"
            invitation_model.save(update_fields=["status"])
            raise InvalidOperation("Invitation is invalid or expired.")

        if invitation_model.email and student.email.lower() != invitation_model.email.lower():
            raise PermissionDenied("Invitation email does not match your account.")

        membership_domain = create_membership(classroom_model, student, "student")

        # update usage count
        invitation_model.increment_usage()

        return membership_domain

    # open join
    return create_membership(classroom_model, student, "student")


@transaction.atomic
def leave_classroom(student: UserModel, classroom_id: int, *, soft_delete: bool = True) -> None:
    """
    Member leaves the classroom.
    - Students cannot leave if they have unfinished lessons/quizzes.
    - Instructor cannot leave if they are the last instructor.
    """

    try:
        membership_model = MembershipModel.objects.select_for_update().get(
            classroom_id=classroom_id, student=student, is_active=True
        )
    except MembershipModel.DoesNotExist:
        raise NotFoundError("Active membership not found.")

    deactivate_membership(
        membership_model,
        allow_self=True,
        soft_delete=soft_delete,
    )


# Instructor/Admin
@transaction.atomic
def add_member(requesting: UserModel, classroom_id: int, user_id: int, role: str = "student") -> MembershipDomain:
    """
    Instructor/Admin adds a member into a classroom.
    """
    try:
        classroom_model = ClassroomModel.objects.get(id=classroom_id)
    except ClassroomModel.DoesNotExist:
        raise NotFoundError("Classroom not found.")

    ensure_is_admin_or_instructor(requesting, classroom_model)

    try:
        user_model = UserModel.objects.get(id=user_id)
    except UserModel.DoesNotExist:
        raise NotFoundError("User not found.")

    return create_membership(classroom_model, user_model, role)


@transaction.atomic
def remove_member(requesting: UserModel, classroom_id: int, member_id: int, *, soft_delete: bool = True) -> None:
    """
    Remove a member from classroom.
    - Instructor may remove students; admin can remove anyone.
    - Instructor cannot remove other instructors (unless admin).
    - Instructor cannot remove the last instructor.
    """

    try:
        classroom_model = ClassroomModel.objects.select_for_update().get(id=classroom_id)
    except ClassroomModel.DoesNotExist:
        raise NotFoundError("Classroom not found.")

    ensure_is_admin_or_instructor(requesting, classroom_model)

    try:
        membership_model = MembershipModel.objects.select_for_update().get(id=member_id, classroom=classroom_model, is_active=True)
    except MembershipModel.DoesNotExist:
        raise NotFoundError("Membership not found.")

    # Only admin can remove instructors
    if (not requesting.is_staff and membership_model.role.lower() in ("instructor", "co-instructor")):
        raise PermissionDenied("Only admin can remove other instructors.")

    deactivate_membership(
        membership_model,
        allow_self=False,
        soft_delete=soft_delete,
    )


@transaction.atomic
def assign_instructor(requesting: UserModel, classroom_id: int, user_id: int, *, soft_delete: bool = True) -> MembershipDomain:
    """
    Assign a user as instructor in a classroom.
    - Only admin or existing instructor can assign.
    - If membership exists → update role.
    - If not exists → create new membership with role=instructor.
    """

    try:
        classroom_model = ClassroomModel.objects.select_for_update().get(id=classroom_id)
    except ClassroomModel.DoesNotExist:
        raise NotFoundError("Classroom not found.")

    ensure_is_admin_or_instructor(requesting, classroom_model)

    try:
        user_model = UserModel.objects.get(id=user_id)
    except UserModel.DoesNotExist:
        raise NotFoundError("User not found.")

    membership_qs = MembershipModel.objects.filter(
        classroom=classroom_model, student=user_model
    )

    if membership_qs.exists():
        membership_model = membership_qs.select_for_update().first()

        if not membership_model.is_active:
            if soft_delete:
                # revive membership
                membership_model.is_active = True
            # else: nếu hard-delete thì thường không revive → raise
            else:
                raise InvalidOperation("Membership exists but inactive. Consider re-adding user.")

        membership_model.role = "instructor"
        membership_model.save(update_fields=["role", "is_active"])
    else:
        membership_model = MembershipModel.objects.create(
            classroom=classroom_model,
            student=user_model,
            role="instructor",
            is_active=True,
        )

    return MembershipDomain.from_model(membership_model)


@transaction.atomic
def change_member_role(requesting: UserModel, classroom_id: int, member_id: int, new_role: str) -> MembershipDomain:
    """
    Change role of a member (student <-> instructor).
    - Admin can change any role.
    - Instructors can change students/co-instructors, not other instructors.
    - Cannot demote the last instructor.
    """

    try:
        classroom_model = ClassroomModel.objects.select_for_update().get(id=classroom_id)
    except ClassroomModel.DoesNotExist:
        raise NotFoundError("Classroom not found.")

    ensure_is_admin_or_instructor(requesting, classroom_model)

    try:
        membership_model = MembershipModel.objects.select_for_update().get(
            id=member_id, classroom=classroom_model, is_active=True
        )
    except MembershipModel.DoesNotExist:
        raise NotFoundError("Membership not found.")

    # Permission checks
    if not requesting.is_staff:
        # Instructors cannot change other instructors
        if membership_model.role.lower() in ("instructor", "co-instructor", "co_instructor"):
            raise PermissionDenied("Only admin can change instructor roles.")

    # If demoting an instructor, ensure not the last one
    if (membership_model.role.lower() in ("instructor", "co-instructor") and new_role.lower() == "student"):
        total_instructors = MembershipModel.objects.filter(
            classroom=classroom_model,
            role="instructor",
            is_active=True
        ).count()
        if total_instructors <= 1:
            raise InvalidOperation("Cannot demote the last instructor.")

    membership_model.role = new_role
    membership_model.save(update_fields=["role"])
    return MembershipDomain.from_model(membership_model)


# def add_member(domain: MembershipDomain) -> MembershipDomain:
#     """Add membership record (teacher adds instructor/co-instructor/student)."""
#     _call_validate(domain)

#     # verify classroom exists
#     try:
#         ClassroomModel.objects.get(pk=domain.classroom_id)
#     except ClassroomModel.DoesNotExist:
#         raise NotFoundError("Classroom not found")

#     try:
#         with transaction.atomic():
#             m, created = MembershipModel.objects.get_or_create(
#                 classroom_id=domain.classroom_id,
#                 student_id=domain.student_id,
#                 defaults={
#                     "role": domain.role,
#                     "joined_on": getattr(domain, "joined_on", timezone.now()),
#                     "is_active": getattr(domain, "is_active", True),
#                 }
#             )
#             if not created:
#                 # update record if different
#                 changed = False
#                 if m.role != domain.role:
#                     m.role = domain.role
#                     changed = True
#                 if not m.is_active and domain.is_active:
#                     m.is_active = True
#                     changed = True
#                 if changed:
#                     m.save()
#     except IntegrityError as e:
#         raise DuplicateError("Member already exists") from e

#     return MembershipDomain.from_model(m)


# def remove_member(classroom_id: Any, student_id: Any) -> None:
#     """Remove membership record (permanent delete)."""
#     try:
#         m = MembershipModel.objects.get(classroom_id=classroom_id, student_id=student_id)
#     except MembershipModel.DoesNotExist:
#         raise NotFoundError("Membership not found")
#     m.delete()


# def change_member_role(domain: MembershipDomain) -> MembershipDomain:
#     """Change existing member role."""
#     if not domain.classroom_id or not domain.student_id:
#         raise DomainValidationError("classroom_id and student_id required")
#     try:
#         m = MembershipModel.objects.get(classroom_id=domain.classroom_id, student_id=domain.student_id)
#     except MembershipModel.DoesNotExist:
#         raise NotFoundError("Membership not found")

#     _call_validate(domain)
#     m.role = domain.role
#     m.save()
#     return MembershipDomain.from_model(m)


def list_members(classroom_id: id, active_only: bool = True) -> List[MembershipDomain]:
    qs = MembershipModel.objects.filter(classroom_id=classroom_id)
    if active_only:
        qs = qs.filter(is_active=True)
    return [MembershipDomain.from_model(m) for m in qs.order_by("joined_on")]

