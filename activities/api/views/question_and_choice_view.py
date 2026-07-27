from typing import Any, Dict
from django.http import HttpResponse
from rest_framework import status, permissions, generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework.parsers import JSONParser

# Import your serializers and services
from activities.serializers import (
    ExerciseModelSerializer,
    QuestionModelSerializer,
    ChoiceModelSerializer,
    StartAttemptSerializer,
    SubmitAnswerSerializer,
    FinalizeAttemptSerializer,
    ExerciseAttemptModelSerializer,
    ExerciseAnswerModelSerializer,
    exercise_domain_to_response,
    attempt_domain_to_response,
)
from activities.services import (
    get_exercise,
    list_exercises,
    save_exercise,
    delete_exercise,
    add_question,
    delete_question,
    add_choice,
    delete_choice,
    start_attempt,
    submit_answer,
    finalize_attempt,
    regrade_attempt,
    get_attempt_summary,
    exercise_stats,
    export_results_csv,
)
from activities.services import ServiceError, NotFoundError, ValidationError, PermissionDenied
from activities.api.permissions import IsAdminOrReadOnly
from activities.models import Choice, Exercise, Question
from activities.services.exercise_access_service import can_manage_exercise

class IsTeacherOrAdmin(permissions.BasePermission):
    """Allow teachers and admins."""
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return bool(
            request.user.is_staff
            or (
                hasattr(request.user, 'role')
                and request.user.role in ['instructor', 'teacher', 'admin']
            )
        )


# -----------------------
# Question & Choice endpoints
# -----------------------
class ExerciseQuestionCreateView(APIView):
    """
    POST /api/activities/exercises/{exercise_id}/questions/  -> add a question under an exercise
    """
    permission_classes = [permissions.IsAuthenticated, IsTeacherOrAdmin]

    def post(self, request: Request, exercise_id: str):
        try:
            exercise = Exercise.objects.select_related(
                "settings", "lesson__module__course"
            ).get(id=exercise_id)
        except Exercise.DoesNotExist:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        if not can_manage_exercise(request.user, exercise):
            return Response({"detail": "Không được phép chỉnh sửa"}, status=status.HTTP_403_FORBIDDEN)
        # Merge exercise_id from URL into data if not provided
        data = request.data.copy()
        if exercise_id and 'exercise' not in data:
            data['exercise'] = exercise_id
        serializer = QuestionModelSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        q_domain = serializer.to_domain()
        try:
            created_q = add_question(exercise_id, q_domain)
        except (ValidationError, ServiceError, NotFoundError) as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(QuestionModelSerializer.from_domain(created_q), status=status.HTTP_201_CREATED)


class QuestionDeleteView(APIView):
    """
    DELETE /api/activities/questions/{question_id}/
    """
    permission_classes = [permissions.IsAuthenticated, IsTeacherOrAdmin]

    def delete(self, request: Request, question_id: str):
        try:
            question = Question.objects.select_related(
                "exercise__settings", "exercise__lesson__module__course"
            ).get(id=question_id)
        except Question.DoesNotExist:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        if not can_manage_exercise(request.user, question.exercise):
            return Response({"detail": "Không được phép chỉnh sửa"}, status=status.HTTP_403_FORBIDDEN)
        try:
            delete_question(question_id)
        except NotFoundError:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class QuestionChoiceCreateView(APIView):
    """
    POST /api/activities/questions/{question_id}/choices/
    """
    permission_classes = [permissions.IsAuthenticated, IsTeacherOrAdmin]

    def post(self, request: Request, question_id: str):
        try:
            question = Question.objects.select_related(
                "exercise__settings", "exercise__lesson__module__course"
            ).get(id=question_id)
        except Question.DoesNotExist:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        if not can_manage_exercise(request.user, question.exercise):
            return Response({"detail": "Không được phép chỉnh sửa"}, status=status.HTTP_403_FORBIDDEN)
        serializer = ChoiceModelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        c_domain = serializer.to_domain()
        try:
            created_c = add_choice(question_id, c_domain)
        except (ValidationError, ServiceError, NotFoundError) as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ChoiceModelSerializer.from_domain(created_c), status=status.HTTP_201_CREATED)


class ChoiceDeleteView(APIView):
    """
    DELETE /api/activities/choices/{choice_id}/
    """
    permission_classes = [permissions.IsAuthenticated, IsTeacherOrAdmin]

    def delete(self, request: Request, choice_id: str):
        try:
            choice = Choice.objects.select_related(
                "question__exercise__settings",
                "question__exercise__lesson__module__course",
            ).get(id=choice_id)
        except Choice.DoesNotExist:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        if not can_manage_exercise(request.user, choice.question.exercise):
            return Response({"detail": "Không được phép chỉnh sửa"}, status=status.HTTP_403_FORBIDDEN)
        try:
            delete_choice(choice_id)
        except NotFoundError:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)
