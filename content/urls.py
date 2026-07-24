# content/api/urls.py
from django.urls import path

from content.api.views import subject_view, course_view, module_view, lesson_view, lesson_version_view, content_block_view, exploration_view, lesson_progress_view, content_library_view

urlpatterns = [
    # ---------------------------
    # Subject
    # ---------------------------
    path("subjects/", subject_view.SubjectListCreateView.as_view(), name="subject-list"),
    path("subjects/<uuid:pk>/", subject_view.SubjectDetailView.as_view(), name="subject-detail"),

    # ---------------------------
    # Course
    # ---------------------------
    path("courses/", course_view.CourseListCreateView.as_view(), name="course-list"),
    path("courses/<uuid:pk>/", course_view.CourseDetailView.as_view(), name="course-detail"),
    path("courses/<uuid:course_id>/publish/", course_view.CoursePublishView.as_view(), name="course-publish"),
    path("courses/<uuid:course_id>/enroll/", course_view.CourseEnrollView.as_view(), name="course-enroll"),

    # ---------------------------
    # Module (nested under course)
    # ---------------------------
    path("courses/<uuid:course_id>/modules/", module_view.ModuleListCreateView.as_view(), name="module-list"),
    path("modules/<uuid:pk>/", module_view.ModuleDetailView.as_view(), name="module-detail"),
    path("courses/<uuid:course_id>/modules/reorder/", module_view.ModuleReorderView.as_view(), name="module-reorder"),

    # ---------------------------
    # Lesson (nested under module)
    # ---------------------------
    path("modules/<uuid:module_id>/lessons/", lesson_view.LessonListCreateView.as_view(), name="lesson-list"),
    path("lessons/<uuid:pk>/", lesson_view.LessonDetailView.as_view(), name="lesson-detail"),
    path("lessons/<uuid:lesson_id>/publish/", lesson_view.LessonPublishView.as_view(), name="lesson-publish"),
    path("lessons/<uuid:lesson_id>/transcribe/", lesson_view.LessonTranscribeView.as_view(), name="lesson-transcribe"),
    path("lessons/<uuid:lesson_id>/progress/", lesson_progress_view.LessonProgressView.as_view(), name="lesson-progress"),
    path("lessons/<uuid:lesson_id>/unlock-check/", lesson_progress_view.LessonUnlockCheckView.as_view(), name="lesson-unlock-check"),

    # ---------------------------
    # Lesson Versions (nested under lesson)
    # ---------------------------
    path("lessons/<uuid:lesson_id>/versions/", lesson_version_view.LessonVersionListCreateView.as_view(), name="lessonversion-list"),
    path("lesson-versions/<uuid:pk>/", lesson_version_view.LessonVersionDetailView.as_view(), name="lessonversion-detail"),
    path("lessons/<uuid:lesson_id>/versions/publish/", lesson_version_view.LessonVersionPublishView.as_view(), name="lessonversion-publish"),

    # ---------------------------
    # Content Blocks (nested under lesson_version)
    # ---------------------------
    path("lesson-versions/<uuid:lesson_version_id>/blocks/", content_block_view.ContentBlockListCreateView.as_view(), name="contentblock-list"),
    path("content-blocks/<uuid:pk>/", content_block_view.ContentBlockDetailView.as_view(), name="contentblock-detail"),

    # ---------------------------
    # Explorations
    # ---------------------------
    path("explorations/", exploration_view.ExplorationListCreateView.as_view(), name="exploration-list"),
    path("explorations/<uuid:pk>/", exploration_view.ExplorationDetailView.as_view(), name="exploration-detail"),
    path("explorations/<uuid:exploration_id>/publish/", exploration_view.ExplorationPublishView.as_view(), name="exploration-publish"),

    # ---------------------------
    # Exploration States
    # ---------------------------
    path("explorations/<uuid:exploration_id>/states/", exploration_view.ExplorationStateListCreateView.as_view(), name="explorationstate-list"),
    path("exploration-states/<uuid:pk>/", exploration_view.ExplorationStateDetailView.as_view(), name="explorationstate-detail"),

    # ---------------------------
    # Exploration Transitions
    # ---------------------------
    path("explorations/<uuid:exploration_id>/transitions/", exploration_view.ExplorationTransitionListCreateView.as_view(), name="explorationtransition-list"),
    path("exploration-transitions/<uuid:pk>/", exploration_view.ExplorationTransitionDetailView.as_view(), name="explorationtransition-detail"),

    # ---------------------------
    # Content Library
    # ---------------------------
    path("content-library/", content_library_view.ContentLibraryListCreateView.as_view(), name="content-library-list"),
    path("content-library/<uuid:id>/", content_library_view.ContentLibraryDetailView.as_view(), name="content-library-detail"),
]
