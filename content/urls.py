# content/api/urls.py
from django.urls import path

from content.api.views import course_view, module_view, lesson_view, lesson_progress_view

urlpatterns = [
    path("courses/", course_view.CourseListCreateView.as_view(), name="course-list"),
    path("courses/<uuid:pk>/", course_view.CourseDetailView.as_view(), name="course-detail"),
    path("courses/<uuid:course_id>/publish/", course_view.CoursePublishView.as_view(), name="course-publish"),
    path("courses/<uuid:course_id>/enroll/", course_view.CourseEnrollView.as_view(), name="course-enroll"),

    path("courses/<uuid:course_id>/modules/", module_view.ModuleListCreateView.as_view(), name="module-list"),
    path("modules/<uuid:pk>/", module_view.ModuleDetailView.as_view(), name="module-detail"),
    path("courses/<uuid:course_id>/modules/reorder/", module_view.ModuleReorderView.as_view(), name="module-reorder"),

    path("modules/<uuid:module_id>/lessons/", lesson_view.LessonListCreateView.as_view(), name="lesson-list"),
    path("lessons/<uuid:pk>/", lesson_view.LessonDetailView.as_view(), name="lesson-detail"),
    path("modules/<uuid:module_id>/lessons/reorder/", lesson_view.LessonReorderView.as_view(), name="lesson-reorder"),
    path("lessons/<uuid:lesson_id>/progress/", lesson_progress_view.LessonProgressView.as_view(), name="lesson-progress"),
    path("lessons/<uuid:lesson_id>/unlock-check/", lesson_progress_view.LessonUnlockCheckView.as_view(), name="lesson-unlock-check"),
]
