from django.urls import path

from school.api.views.school_views import (
    SchoolListCreateView, SchoolDetailView
)
from school.api.views.classroom_views import (
    ClassroomListCreateView, ClassroomDetailView
)
from school.api.views.membership_views import (
    MembershipListCreateView, MembershipDetailView
)
from school.api.views.enrollment_views import (
    EnrollmentListCreateView, EnrollmentDetailView
)
from school.api.views.invitation_views import (
    InvitationListCreateView, InvitationAcceptView, InvitationRevokeView
)

urlpatterns = [
    # ---------------- School ----------------
    path("schools/", SchoolListCreateView.as_view(), name="school-list-create"),
    path("schools/<uuid:pk>/", SchoolDetailView.as_view(), name="school-detail"),

    # ---------------- Classroom ----------------
    path("schools/<uuid:school_id>/classrooms/", ClassroomListCreateView.as_view(), name="classroom-list-create"),
    path("classrooms/<uuid:pk>/", ClassroomDetailView.as_view(), name="classroom-detail"),

    # ---------------- Membership ----------------
    path("classrooms/<uuid:classroom_id>/members/", MembershipListCreateView.as_view(), name="membership-list-create"),
    path("classrooms/<uuid:classroom_id>/members/<uuid:user_id>/", MembershipDetailView.as_view(), name="membership-detail"),

    # ---------------- Enrollment ----------------
    path("classrooms/<uuid:classroom_id>/enrollments/", EnrollmentListCreateView.as_view(), name="enrollment-list-create"),
    path("enrollments/<uuid:pk>/", EnrollmentDetailView.as_view(), name="enrollment-detail"),

    # ---------------- Invitation ----------------
    path("classrooms/<uuid:classroom_id>/invitations/", InvitationListCreateView.as_view(), name="invitation-list-create"),
    path("invitations/<uuid:pk>/accept/", InvitationAcceptView.as_view(), name="invitation-accept"),
    path("invitations/<uuid:pk>/revoke/", InvitationRevokeView.as_view(), name="invitation-revoke"),
]
