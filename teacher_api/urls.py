from django.urls import path
from teacher_api.views import TeacherDashboardView, TeacherStudentsView
from teacher_api.views.feedback_view import TeacherFeedbackView
from teacher_api.views.notifications_view import (
    TeacherNotificationsView,
    TeacherNotificationReadView,
)
from teacher_api.views.lesson_question_view import TeacherLessonQuestionView

app_name = 'teacher_api'

urlpatterns = [
    path('dashboard/', TeacherDashboardView.as_view(), name='dashboard'),
    path('students/', TeacherStudentsView.as_view(), name='students'),
    path('students/feedback/', TeacherFeedbackView.as_view(), name='feedback'),
    path('notifications/', TeacherNotificationsView.as_view(), name='notifications'),
    path('notifications/<uuid:id>/read/', TeacherNotificationReadView.as_view(), name='notification-read'),
    path('lesson-questions/', TeacherLessonQuestionView.as_view(), name='lesson-questions'),
    path('lesson-questions/<uuid:pk>/reply/', TeacherLessonQuestionView.as_view(), name='lesson-question-reply'),
]




