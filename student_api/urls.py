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
    StudentLessonQuestionReactionView,
    StudentLessonQuestionQuestionReactionView,
    StudentLessonQuestionReportView,
    StudentLessonQuestionAIAnswerView,
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
    AITutorHintView,
    AITutorExplainView,
    AITutorEncourageView,
    AITutorClearHistoryView,
    AITutorAnalyzeView,
    AITutorPracticeView,
    AITutorPracticeSubmitView,
    AITutorDailyReportView,
    AITutorWeaknessNotificationView,
    AITutorVideoQuestionView,
)
from ai_personalization.api.tts_views import TextToSpeechView
from gamification.api.views import (
    StudentGameListView,
    StudentGameDetailView,
    StudentGameSessionView,
    StudentGameLeaderboardView,
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
    # Allow both pk and explicit question_id for reaction endpoint
    path('lesson-questions/<uuid:pk>/react/', StudentLessonQuestionQuestionReactionView.as_view(), name='lesson-question-question-reaction'),
    # AI answer - phải đặt trước route detail để không bị match sai
    path('lesson-questions/<uuid:question_id>/ai-answer/', StudentLessonQuestionAIAnswerView.as_view(), name='lesson-question-ai-answer'),
    path('lesson-questions/<uuid:pk>/', StudentLessonQuestionView.as_view(), name='lesson-question-detail'),
    path('lesson-question-replies/<uuid:reply_id>/react/', StudentLessonQuestionReactionView.as_view(), name='lesson-question-reaction'),
    path('lesson-question-replies/<uuid:reply_id>/', StudentLessonQuestionReplyView.as_view(), name='lesson-question-reply-detail'),
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
    
    # AI Tutor
    path('ai/tutor/chat/', AITutorChatView.as_view(), name='ai-tutor-chat'),
    path('ai/tutor/hint/', AITutorHintView.as_view(), name='ai-tutor-hint'),
    path('ai/tutor/explain/', AITutorExplainView.as_view(), name='ai-tutor-explain'),
    path('ai/tutor/encourage/', AITutorEncourageView.as_view(), name='ai-tutor-encourage'),
    path('ai/tutor/history/', AITutorClearHistoryView.as_view(), name='ai-tutor-history'),
    path('ai/tutor/analyze/', AITutorAnalyzeView.as_view(), name='ai-tutor-analyze'),
    path('ai/tutor/practice/', AITutorPracticeView.as_view(), name='ai-tutor-practice'),
    path('ai/tutor/practice/submit/', AITutorPracticeSubmitView.as_view(), name='ai-tutor-practice-submit'),
    path('ai/tutor/daily-report/', AITutorDailyReportView.as_view(), name='ai-tutor-daily-report'),
    path('ai/tutor/notify-weakness/', AITutorWeaknessNotificationView.as_view(), name='ai-tutor-notify-weakness'),
    path('ai/tutor/video-question/', AITutorVideoQuestionView.as_view(), name='ai-tutor-video-question'),
    path('ai/tts/', TextToSpeechView.as_view(), name='ai-tts'),
    
    # Games
    path('games/', StudentGameListView.as_view(), name='game-list'),
    path('games/<uuid:game_id>/', StudentGameDetailView.as_view(), name='game-detail'),
    path('games/<uuid:game_id>/leaderboard/', StudentGameLeaderboardView.as_view(), name='game-leaderboard'),
    path('games/<uuid:game_id>/<str:action>/', StudentGameSessionView.as_view(), name='game-session'),
]
