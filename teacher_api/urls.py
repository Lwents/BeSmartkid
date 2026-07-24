from django.urls import path
from teacher_api.views import TeacherDashboardView, TeacherStudentsView
from teacher_api.views.feedback_view import TeacherFeedbackView, TeacherFeedbackListView
from teacher_api.views.notifications_view import (
    TeacherNotificationsView,
    TeacherNotificationReadView,
    TeacherNotificationReadAllView,
)
from teacher_api.views.lesson_question_view import TeacherLessonQuestionView
from gamification.api.views import (
    TeacherGameListView,
    TeacherGameDetailView,
    TeacherGameStatsView,
    TeacherGameAIGenerateView,
)

app_name = 'teacher_api'

urlpatterns = [
    path('dashboard/', TeacherDashboardView.as_view(), name='dashboard'),
    path('students/', TeacherStudentsView.as_view(), name='students'),
    path('students/feedback/', TeacherFeedbackView.as_view(), name='feedback'),
    path('students/feedback/list/', TeacherFeedbackListView.as_view(), name='feedback-list'),
    # Notifications
    path('notifications/', TeacherNotificationsView.as_view(), name='notifications'),
    path('notifications/<uuid:id>/read/', TeacherNotificationReadView.as_view(), name='notification-read'),
    path('notifications/read-all/', TeacherNotificationReadAllView.as_view(), name='notification-read-all'),
    # Lesson Q&A
    path('lesson-questions/', TeacherLessonQuestionView.as_view(), name='lesson-questions'),
    path('lesson-questions/<uuid:pk>/reply/', TeacherLessonQuestionView.as_view(), name='lesson-question-reply'),
    path('lesson-question-replies/<uuid:pk>/', TeacherLessonQuestionView.as_view(), name='lesson-question-reply-detail'),
    # Games
    path('games/', TeacherGameListView.as_view(), name='game-list'),
    path('games/ai-generate/', TeacherGameAIGenerateView.as_view(), name='game-ai-generate'),
    path('games/<uuid:game_id>/', TeacherGameDetailView.as_view(), name='game-detail'),
    path('games/<uuid:game_id>/stats/', TeacherGameStatsView.as_view(), name='game-stats'),
]





