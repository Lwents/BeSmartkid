from django.urls import path
from admin_api.views import (
    AdminDashboardView, AdminActiveUsersRealtimeView,
    AdminCourseListView, AdminCourseDetailView,
    AdminCourseApproveView, AdminCourseRejectView,
    AdminCoursePublishView, AdminCourseUnpublishView,
    AdminCourseArchiveView, AdminCourseRestoreView,
    AdminLessonVideoDeleteView,
    AdminUserReportView,
    AdminLearningReportView, AdminContentReportView,
    AdminSystemConfigView, AdminSystemBackupView, AdminSystemRestoreView,
    AdminSystemHealthView,
    AdminActivityLogView,
    AdminSecurityPolicyView,
    AdminSessionListView,
    AdminSessionRevokeView,
)
from admin_api.views.notifications_view import (
    AdminNotificationsView,
    AdminNotificationReadView,
    AdminNotificationReadAllView,
)

app_name = 'admin_api'

urlpatterns = [
    # Dashboard
    path('dashboard/', AdminDashboardView.as_view(), name='dashboard'),
    path('dashboard/active-users/', AdminActiveUsersRealtimeView.as_view(), name='dashboard-active-users'),

    path('courses/', AdminCourseListView.as_view(), name='course-list'),
    path('courses/<uuid:pk>/', AdminCourseDetailView.as_view(), name='course-detail'),
    path(
        'courses/<uuid:pk>/lessons/<uuid:lesson_id>/video/',
        AdminLessonVideoDeleteView.as_view(),
        name='course-lesson-video-delete',
    ),
    path('courses/<uuid:pk>/approve/', AdminCourseApproveView.as_view(), name='course-approve'),
    path('courses/<uuid:pk>/reject/', AdminCourseRejectView.as_view(), name='course-reject'),
    path('courses/<uuid:pk>/publish/', AdminCoursePublishView.as_view(), name='course-publish'),
    path('courses/<uuid:pk>/unpublish/', AdminCourseUnpublishView.as_view(), name='course-unpublish'),
    path('courses/<uuid:pk>/archive/', AdminCourseArchiveView.as_view(), name='course-archive'),
    path('courses/<uuid:pk>/restore/', AdminCourseRestoreView.as_view(), name='course-restore'),

    # Reports
    path('reports/users/', AdminUserReportView.as_view(), name='report-users'),
    path('reports/learning/', AdminLearningReportView.as_view(), name='report-learning'),
    path('reports/content/', AdminContentReportView.as_view(), name='report-content'),

    # System
    path('system/config/', AdminSystemConfigView.as_view(), name='system-config'),
    path('system/backups/', AdminSystemBackupView.as_view(), name='system-backups'),
    path('system/restore/', AdminSystemRestoreView.as_view(), name='system-restore'),
    path('system/health/', AdminSystemHealthView.as_view(), name='system-health'),

    # Activity Logs
    path('activity-logs/', AdminActivityLogView.as_view(), name='activity-logs'),

    # Security
    path('security/policy/', AdminSecurityPolicyView.as_view(), name='security-policy'),
    path('security/sessions/', AdminSessionListView.as_view(), name='security-sessions'),
    path('security/sessions/<str:jti>/', AdminSessionRevokeView.as_view(), name='security-session-revoke'),
    
    # Notifications
    path('notifications/', AdminNotificationsView.as_view(), name='notifications'),
    path('notifications/read-all/', AdminNotificationReadAllView.as_view(), name='notifications-read-all'),
    path('notifications/<uuid:id>/read/', AdminNotificationReadView.as_view(), name='notification-read'),
]
