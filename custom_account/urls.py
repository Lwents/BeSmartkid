from django.urls import path, re_path
from rest_framework_simplejwt.views import TokenRefreshView  # For token refresh endpoint
from dj_rest_auth.views import LogoutView

from custom_account.api.views.auth_view import (
    RegisterView,
    CustomLoginView,
    AdminLoginAsUserView,
    AdminRefreshUserAccessView,
    AdminLogoutUserView,
    AdvancedPasswordResetConfirmView,
    ResetPasswordRequestView,
    ResetPasswordConfirmView,
)
from custom_account.api.views.user_view import (
    AdminUserListView,
    CurrentUserDetailView,
    ChangePasswordView,
    AdminUserDetailView,
    AdminChangePasswordView,
    AdminMaintenanceView,
    PasswordChangeOTPRequestView,
    PasswordChangeOTPConfirmView,
    AdminBulkChangeRoleView,
    AdminBulkLockView,
    AdminBulkUnlockView,
    AdminBulkBanView,
    AdminUserExportView,
)
from custom_account.api.views.profile_view import UserProfileView, AdminProfileListView, AdminProfileDetailView

urlpatterns = [
    path("register/", RegisterView.as_view(), name="account-register"),
    path('login/', CustomLoginView.as_view(), name='account_login'),
    path('refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path("user/", CurrentUserDetailView.as_view(), name="current-user"),
    path("profile/", UserProfileView.as_view(), name="account-profile"),
    path("password/change/", ChangePasswordView.as_view(), name="account-change-password"),
    path("password/change/request-otp/", PasswordChangeOTPRequestView.as_view(), name="account-change-password-request-otp"),
    path("password/change/confirm-otp/", PasswordChangeOTPConfirmView.as_view(), name="account-change-password-confirm-otp"),
    path('password/reset/', ResetPasswordRequestView.as_view(), name='password_reset_request'),
    path('password/reset/confirm/', ResetPasswordConfirmView.as_view(), name='password_reset_confirm'),
    re_path(r'^password/reset/confirm/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,32})/$', AdvancedPasswordResetConfirmView.as_view(), name='password_reset_confirm_legacy'),
    
    # path("consents/", ParentalConsentListView.as_view(), name="account-consents-list"),
    # path("consents/grant/", ParentalConsentCreateView.as_view(), name="account-consents-grant"),
    # path("consents/revoke/", ParentalConsentRevokeView.as_view(), name="account-consents-revoke"),

    path("admin/login/<int:user_id>/", AdminLoginAsUserView.as_view(), name="admin-login-as-user"),
    path('admin/refresh-access/<int:user_id>/', AdminRefreshUserAccessView.as_view(), name='admin_refresh_access'),
    path('admin/logout-user/<int:user_id>/', AdminLogoutUserView.as_view(), name='admin_logout_user'),
    path("admin/users/", AdminUserListView.as_view(), name="admin-user-list"),
    path("admin/users/export/", AdminUserExportView.as_view(), name="admin-user-export"),
    path("admin/users/bulk/role/", AdminBulkChangeRoleView.as_view(), name="admin-bulk-role"),
    path("admin/users/bulk/lock/", AdminBulkLockView.as_view(), name="admin-bulk-lock"),
    path("admin/users/bulk/unlock/", AdminBulkUnlockView.as_view(), name="admin-bulk-unlock"),
    path("admin/users/bulk/ban/", AdminBulkBanView.as_view(), name="admin-bulk-ban"),
    path('admin/maintenance/', AdminMaintenanceView.as_view(), name='admin-system-maintenance'),
    path("admin/users/<int:pk>/", AdminUserDetailView.as_view(), name="admin-user-detail"),
    path("admin/profiles/", AdminProfileListView.as_view(), name="admin-profile-list"),
    path("admin/profiles/<int:user_id>/", AdminProfileDetailView.as_view(), name="admin-profile"),
    path("admin/password/set/<int:user_id>/", AdminChangePasswordView.as_view(), name="admin-set-password"),
]
