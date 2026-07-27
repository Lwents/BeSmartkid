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
from activities.services import attempt_service, exercise_service, analytic_service
from activities.models import ExerciseAttempt
from custom_account.models import Profile
from activities.services.attempt_service import manual_grade_answer
from activities.services import ServiceError, NotFoundError, ValidationError, PermissionDenied
from activities.api.permissions import IsAdminOrReadOnly
from activities.models import Exercise
from activities.services.exercise_access_service import (
    can_manage_exercise,
    student_can_access_exercise,
)

class IsTeacherOrAdmin(permissions.BasePermission):
    """Allow teachers/instructors and admins."""
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return bool(
            request.user.is_staff or 
            (hasattr(request.user, 'role') and request.user.role in ['instructor', 'teacher', 'admin'])
        )



class RegradeAttemptView(APIView):
    """
    POST /api/activities/attempts/{attempt_id}/regrade/
    Admin/instructor only.
    """
    permission_classes = [permissions.IsAuthenticated, IsTeacherOrAdmin]

    def post(self, request: Request, attempt_id: str):
        try:
            attempt = ExerciseAttempt.objects.select_related(
                "exercise__settings", "exercise__lesson__module__course"
            ).get(id=attempt_id)
        except ExerciseAttempt.DoesNotExist:
            return Response({"detail": "Attempt not found"}, status=status.HTTP_404_NOT_FOUND)
        if not can_manage_exercise(request.user, attempt.exercise):
            return Response({"detail": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)
        try:
            result = attempt_service.regrade_attempt(attempt_id)
        except NotFoundError:
            return Response({"detail": "Attempt not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(result, status=status.HTTP_200_OK)


class ManualGradeView(APIView):
    """
    POST /api/activities/attempts/{attempt_id}/grade/
    Body: {"question_id": "...", "score": 2.0, "comment": "notes"}
    Admin/instructor only.
    """
    permission_classes = [permissions.IsAuthenticated, IsTeacherOrAdmin]

    def post(self, request: Request, attempt_id: str):
        data = request.data
        qid = data.get("question_id")
        score = data.get("score")
        comment = data.get("comment")
        if qid is None or score is None:
            return Response({"detail": "question_id and score are required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            # call service function (we expect it to exist in services.activities)
            answer_domain = manual_grade_answer(attempt_id, qid, request.user, float(score), comment)
        except NotFoundError:
            return Response({"detail": "Attempt or answer not found"}, status=status.HTTP_404_NOT_FOUND)
        except PermissionDenied:
            return Response({"detail": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)
        except ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(ExerciseAnswerModelSerializer.from_domain(answer_domain), status=status.HTTP_200_OK)


class ExerciseStatsView(APIView):
    """
    GET /api/activities/exercises/{exercise_id}/stats/
    Returns exercise statistics. If user is authenticated, also includes ranking data.
    For students: returns ranking with their position.
    For teachers/admins: returns full stats.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request, exercise_id: str):
        try:
            exercise = Exercise.objects.select_related(
                "settings", "lesson__module__course"
            ).get(id=exercise_id)
        except Exercise.DoesNotExist:
            return Response({"detail": "Exercise not found"}, status=status.HTTP_404_NOT_FOUND)
        if not (
            can_manage_exercise(request.user, exercise)
            or student_can_access_exercise(request.user, exercise)
        ):
            return Response({"detail": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)
        try:
            from activities.services.analytic_service import exercise_stats, exercise_ranking
            
            # Get basic stats
            stats = exercise_stats(exercise_id)
            
            # Add ranking data if user is authenticated
            # For students, include their rank; for teachers, include top students
            ranking_data = exercise_ranking(exercise_id, user_id=request.user.id if request.user.is_authenticated else None)
            stats.update(ranking_data)
            
        except NotFoundError:
            return Response({"detail": "Exercise not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(stats)


class ExerciseAttemptsListView(APIView):
    """
    GET /api/activities/exercises/{exercise_id}/attempts/
    Returns list of attempts for an exercise. Admin/instructor only.
    """
    permission_classes = [permissions.IsAuthenticated, IsTeacherOrAdmin]

    def get(self, request: Request, exercise_id: str):
        try:
            # Verify exercise exists
            exercise = Exercise.objects.select_related(
                "settings", "lesson__module__course"
            ).get(id=exercise_id)
        except Exercise.DoesNotExist:
            return Response({"detail": "Exercise not found"}, status=status.HTTP_404_NOT_FOUND)
        if not can_manage_exercise(request.user, exercise):
            return Response({"detail": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)
        
        # Get all attempts for this exercise
        attempts = ExerciseAttempt.objects.filter(exercise_id=exercise_id).select_related('student', 'student__profile').order_by('-finished_at', '-started_at')
        
        # Build response
        attempts_data = []
        for attempt in attempts:
            # Get student name from profile.display_name or username
            student_name = 'Unknown'
            student_class = ''
            if attempt.student:
                # ensure profile exists
                profile, _ = Profile.objects.get_or_create(user=attempt.student, defaults={"language": "vietnamese"})
                if hasattr(attempt.student, 'profile') and attempt.student.profile and attempt.student.profile.display_name:
                    student_name = attempt.student.profile.display_name
                else:
                    student_name = attempt.student.username or 'Unknown'
                if profile:
                    meta = profile.metadata or {}
                    student_class = getattr(profile, "class_name", "") or meta.get("class_name", "")
            
            attempts_data.append({
                'id': str(attempt.id),
                'student_id': str(attempt.student.id) if attempt.student else None,
                'student_name': student_name,
                'class_name': student_class,
                'class_code': student_class,  # alias for FE compatibility
                'student_class_code': student_class,
                'started_at': attempt.started_at.isoformat() if attempt.started_at else None,
                'finished_at': attempt.finished_at.isoformat() if attempt.finished_at else None,
                'score': float(attempt.score) if attempt.score else None,
                'status': 'submitted' if attempt.finished_at else 'pending',
            })
        
        return Response(attempts_data, status=status.HTTP_200_OK)


class ExportResultsView(APIView):
    """
    GET /api/activities/exercises/{exercise_id}/export/
    Returns CSV file attachment. Admin/instructor only.
    """
    permission_classes = [permissions.IsAuthenticated, IsTeacherOrAdmin]

    def get(self, request: Request, exercise_id: str):
        try:
            exercise = Exercise.objects.select_related(
                "settings", "lesson__module__course"
            ).get(id=exercise_id)
        except Exercise.DoesNotExist:
            return Response({"detail": "Exercise not found"}, status=status.HTTP_404_NOT_FOUND)
        if not can_manage_exercise(request.user, exercise):
            return Response({"detail": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)
        try:
            filename, content = analytic_service.export_results_csv(exercise_id)
        except NotFoundError:
            return Response({"detail": "Exercise not found"}, status=status.HTTP_404_NOT_FOUND)
        resp = HttpResponse(content, content_type="text/csv")
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp
