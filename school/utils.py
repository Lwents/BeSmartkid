from typing import Optional, List

from custom_account.models import UserModel
from school.models import MembershipModel, ClassroomModel
from school.domains.class_domain import ClassroomDomain
from school.api.permissions import NotFoundError



def list_classrooms_for_user(user: UserModel, *, role_filter: Optional[str] = None) -> List[ClassroomDomain]:
    """
    Return list of classrooms the user participates in (role_filter optional).
    """
    memberships = MembershipModel.objects.filter(student=user, is_active=True)
    if role_filter:
        memberships = memberships.filter(role__iexact=role_filter)
    classroom_ids = memberships.values_list("classroom_id", flat=True).distinct()
    classrooms = ClassroomModel.objects.filter(id__in=classroom_ids)
    return [ClassroomDomain.from_model(cls)  for cls in classrooms]


def get_classroom_domain(classroom_id: int) -> ClassroomDomain:
    try:
        classroom_model = ClassroomDomain.objects.get(id=classroom_id)
    except ClassroomDomain.DoesNotExist:
        raise NotFoundError("Classroom not found.")
    return ClassroomDomain.from_model(classroom_model)