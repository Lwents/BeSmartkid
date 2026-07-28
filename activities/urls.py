# urls/activities.py
from django.urls import path
from activities.api.views import (
    ExerciseListCreateView, ExerciseDetailView,
    ExerciseQuestionCreateView, QuestionDeleteView,
    QuestionChoiceCreateView, ChoiceDeleteView,
    StartAttemptView, SubmitAnswerView, FinalizeAttemptView, AttemptSummaryView,
    ExerciseStatsView, ExerciseAttemptsListView,
    RegradeAttemptView, ManualGradeView, ExportResultsView,
    GenerateQuestionsAIView,
)

app_name = "activities"

urlpatterns = [
    path("exercises/", ExerciseListCreateView.as_view(), name="exercise-list"),
    path("exercises/<uuid:exercise_id>/", ExerciseDetailView.as_view(), name="exercise-detail"),
    path("exercises/<uuid:exercise_id>/questions/", ExerciseQuestionCreateView.as_view(), name="exercise-add-question"),
    path("questions/<uuid:question_id>/", QuestionDeleteView.as_view(), name="question-delete"),
    path("questions/<uuid:question_id>/choices/", QuestionChoiceCreateView.as_view(), name="question-add-choice"),
    path("choices/<uuid:choice_id>/", ChoiceDeleteView.as_view(), name="choice-delete"),

    path("exercises/<uuid:exercise_id>/start/", StartAttemptView.as_view(), name="start-attempt"),
    path("attempts/<uuid:attempt_id>/answers/", SubmitAnswerView.as_view(), name="submit-answer"),
    path("attempts/<uuid:attempt_id>/finalize/", FinalizeAttemptView.as_view(), name="finalize-attempt"),
    path("attempts/<uuid:attempt_id>/", AttemptSummaryView.as_view(), name="attempt-summary"),
    path("attempts/<uuid:attempt_id>/regrade/", RegradeAttemptView.as_view(), name="regrade-attempt"),
    path("attempts/<uuid:attempt_id>/grade/", ManualGradeView.as_view(), name="manual-grade"),

    path("exercises/<uuid:exercise_id>/stats/", ExerciseStatsView.as_view(), name="exercise-stats"),
    path("exercises/<uuid:exercise_id>/attempts/", ExerciseAttemptsListView.as_view(), name="exercise-attempts-list"),
    path("exercises/<uuid:exercise_id>/export/", ExportResultsView.as_view(), name="exercise-export"),
    path("ai/generate-questions/", GenerateQuestionsAIView.as_view(), name="generate-questions-ai"),
]
