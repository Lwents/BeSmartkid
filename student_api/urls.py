from django.urls import path
from student_api.views import (
    StudentDashboardView,
    StudentMyCoursesView,
    StudentCourseCatalogView,
    StudentCourseDetailView,
    StudentCoursePlayerView,
    StudentLearningPathView,
    StudentLearningPathManageView,
    StudentExamsListView,
    StudentExamDetailView,
    StudentExamStartView,
    StudentExamSubmitView,
    StudentExamResultView,
    StudentExamRankingView,
    StudentCertificatesView,
    StudentProfileView,
    StudentChangePasswordView,
    StudentParentViewView,
    StudentLessonQuestionView,
    StudentLessonQuestionReplyView,
    StudentLessonQuestionQuestionReactionView,
    StudentLessonQuestionReportView,
)
from student_api.views.notifications_view import (
    StudentNotificationsView,
    StudentNotificationReadView,
    StudentNotificationReadAllView,
)
from student_api.views.ai_learning_view import (
    AILearningAnalyzerView,
    AIAssessmentView,
    AIAssessmentResultView,
    StreakRestoreView,
)
from ai_personalization.api.tutor_views import (
    AITutorChatView,
    AITutorClearHistoryView,
)

app_name = 'student_api'

urlpatterns = [
    # Dashboard
    path('dashboard/', StudentDashboardView.as_view(), name='dashboard'),
    
    # Courses
    path('courses/', StudentMyCoursesView.as_view(), name='my-courses'),
    path('catalog/', StudentCourseCatalogView.as_view(), name='catalog'),
    path('courses/<uuid:pk>/', StudentCourseDetailView.as_view(), name='course-detail'),
    path('courses/<uuid:pk>/player/', StudentCoursePlayerView.as_view(), name='course-player'),
    path('courses/<uuid:pk>/player/<uuid:lesson_id>/', StudentCoursePlayerView.as_view(), name='course-player-lesson'),
    path('learning-path/', StudentLearningPathView.as_view(), name='learning-path'),
    path('learning-path/manage/', StudentLearningPathManageView.as_view(), name='learning-path-manage'),
    path('lesson-questions/', StudentLessonQuestionView.as_view(), name='lesson-question'),
    path('lesson-questions/<uuid:pk>/reply/', StudentLessonQuestionReplyView.as_view(), name='lesson-question-reply'),
    path('lesson-questions/<uuid:pk>/react/', StudentLessonQuestionQuestionReactionView.as_view(), name='lesson-question-question-reaction'),
    path('lesson-questions/<uuid:pk>/', StudentLessonQuestionView.as_view(), name='lesson-question-detail'),
    path('lesson-question-report/', StudentLessonQuestionReportView.as_view(), name='lesson-question-report'),
    
    # Exams
    path('exams/', StudentExamsListView.as_view(), name='exams-list'),
    path('exams/<uuid:pk>/', StudentExamDetailView.as_view(), name='exam-detail'),
    path('exams/<uuid:pk>/start/', StudentExamStartView.as_view(), name='exam-start'),
    path('exams/<uuid:pk>/submit/<uuid:attempt_id>/', StudentExamSubmitView.as_view(), name='exam-submit'),
    path('exams/<uuid:pk>/result/<uuid:attempt_id>/', StudentExamResultView.as_view(), name='exam-result'),
    path('exams/<uuid:pk>/ranking/', StudentExamRankingView.as_view(), name='exam-ranking'),
    path('exams/certificates/', StudentCertificatesView.as_view(), name='certificates'),
    
    # Account
    path('account/profile/', StudentProfileView.as_view(), name='profile'),
    path('account/change-password/', StudentChangePasswordView.as_view(), name='change-password'),
    path('account/parent/', StudentParentViewView.as_view(), name='parent'),
    
    # Notifications
    path('notifications/', StudentNotificationsView.as_view(), name='notifications'),
    path('notifications/<uuid:id>/read/', StudentNotificationReadView.as_view(), name='notification-read'),
    path('notifications/read-all/', StudentNotificationReadAllView.as_view(), name='notification-read-all'),
    
    # AI Learning
    path('ai/learning-analyzer/', AILearningAnalyzerView.as_view(), name='ai-learning-analyzer'),
    path('ai/assessment/', AIAssessmentView.as_view(), name='ai-assessment'),
    path('ai/assessment/result/', AIAssessmentResultView.as_view(), name='ai-assessment-result'),
    path('ai/learning/restore-streak/', StreakRestoreView.as_view(), name='restore-streak'),
    
    path('ai/tutor/chat/', AITutorChatView.as_view(), name='ai-tutor-chat'),
    path('ai/tutor/history/', AITutorClearHistoryView.as_view(), name='ai-tutor-history'),
]
