"""URL configuration for Assignment API."""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from assignments.api.views.assignment_view import AssignmentViewSet

router = DefaultRouter()
router.register(r'assignments', AssignmentViewSet, basename='assignment')

urlpatterns = [
    path('', include(router.urls)),
]