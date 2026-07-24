from django.urls import path
from .views import TeacherEventListView, TeacherEventDetailView, UpcomingEventsView

urlpatterns = [
    path('teacher/', TeacherEventListView.as_view(), name='teacher-events'),
    path('teacher/<uuid:event_id>/', TeacherEventDetailView.as_view(), name='teacher-event-detail'),
    path('upcoming/', UpcomingEventsView.as_view(), name='upcoming-events'),
]
