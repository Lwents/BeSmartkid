from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from dj_rest_auth.views import LogoutView

from custom_account.api.views.auth_view import (
    RegisterView,
    CustomLoginView,
    ResetPasswordRequestView,
    ResetPasswordConfirmView,
)
from custom_account.api.views.user_view import (
    AdminUserListView,
    ChangePasswordView,
    AdminUserDetailView,
    AdminChangePasswordView,
)
from custom_account.api.views.profile_view import UserProfileView

urlpatterns = [
    path("register/", RegisterView.as_view(), name="account-register"),
    path('login/', CustomLoginView.as_view(), name='account_login'),
    path('refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path("profile/", UserProfileView.as_view(), name="account-profile"),
    path("password/change/", ChangePasswordView.as_view(), name="account-change-password"),
    path('password/reset/', ResetPasswordRequestView.as_view(), name='password_reset_request'),
    path('password/reset/confirm/', ResetPasswordConfirmView.as_view(), name='password_reset_confirm'),
    path("admin/users/", AdminUserListView.as_view(), name="admin-user-list"),
    path("admin/users/<int:pk>/", AdminUserDetailView.as_view(), name="admin-user-detail"),
    path("admin/password/set/<int:user_id>/", AdminChangePasswordView.as_view(), name="admin-set-password"),
]
