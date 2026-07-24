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


# -----------------------
# Attempt endpoints
# -----------------------
class StartAttemptView(APIView):
    """
    POST /api/activities/exercises/{exercise_id}/start/
    Starts an attempt for the authenticated student.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request, exercise_id: str):
        # we expect the current authenticated user is the student
        try:
            attempt_domain = start_attempt(exercise_id, request.user)
        except NotFoundError:
            return Response({"detail": "Exercise not found"}, status=status.HTTP_404_NOT_FOUND)
        except ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except PermissionDenied as e:
            return Response({"detail": str(e)}, status=status.HTTP_403_FORBIDDEN)

        # return attempt summary (domain -> response)
        return Response(ExerciseAttemptModelSerializer.from_domain(attempt_domain), status=status.HTTP_201_CREATED)


class SubmitAnswerView(APIView):
    """
    POST /api/activities/attempts/{attempt_id}/answers/
    Payload: { "question_id": "...", "answer": {...} }
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request, attempt_id: str):
        serializer = SubmitAnswerSerializer(data={"attempt_id": attempt_id, **request.data})
        serializer.is_valid(raise_exception=True)
        try:
            ans_domain = submit_answer(
                attempt_id=attempt_id,
                question_id=str(serializer.validated_data["question_id"]),
                answer_payload=serializer.validated_data["answer"],
                actor_user=request.user,
            )
        except NotFoundError as e:
            return Response({"detail": str(e)}, status=status.HTTP_404_NOT_FOUND)
        except ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except PermissionDenied as e:
            return Response({"detail": str(e)}, status=status.HTTP_403_FORBIDDEN)

        return Response(ExerciseAnswerModelSerializer.from_domain(ans_domain), status=status.HTTP_200_OK)


class FinalizeAttemptView(APIView):
    """
    POST /api/activities/attempts/{attempt_id}/finalize/
    Optional payload: { "force": true } (instructor override)
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request, attempt_id: str):
        serializer = FinalizeAttemptSerializer(data={"attempt_id": attempt_id, **request.data})
        serializer.is_valid(raise_exception=True)
        force = serializer.validated_data.get("force", False)
        try:
            summary = finalize_attempt(attempt_id, actor_user=request.user, force=force)
        except NotFoundError:
            return Response({"detail": "Attempt not found"}, status=status.HTTP_404_NOT_FOUND)
        except PermissionDenied as e:
            return Response({"detail": str(e)}, status=status.HTTP_403_FORBIDDEN)
        except ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # Gửi thông báo gợi ý cải thiện nếu có câu sai
        self._send_improvement_notification(request.user, summary)

        return Response(summary, status=status.HTTP_200_OK)
    
    def _send_improvement_notification(self, user, summary):
        """Gửi thông báo gợi ý cải thiện dựa trên câu trả lời sai"""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            score = summary.get('score', 0)
            total = summary.get('total_score', 100)
            percent = (score / total * 100) if total > 0 else 0
            
            # Chỉ gửi thông báo nếu điểm < 80%
            if percent >= 80:
                return
            
            # Lấy các câu sai
            wrong_answers = []
            answers = summary.get('answers', [])
            for ans in answers:
                if not ans.get('is_correct', True):
                    wrong_answers.append({
                        'question': ans.get('question_text', ''),
                        'student_answer': ans.get('student_answer', ''),
                        'correct_answer': ans.get('correct_answer', ''),
                    })
            
            if not wrong_answers:
                return
            
            # Gọi AI để tạo gợi ý cải thiện
            from ai_personalization.ai_tutor import ai_tutor
            
            # Lấy thông tin học sinh
            student_grade = 1
            if hasattr(user, 'profile'):
                student_grade = getattr(user.profile, 'grade', 1) or 1
            
            # Tạo prompt cho AI
            wrong_topics = [w['question'][:50] for w in wrong_answers[:3]]
            
            ai_suggestion = ai_tutor.generate_improvement_suggestion(
                wrong_answers=wrong_answers[:3],
                score_percent=percent,
                student_grade=student_grade
            )
            
            if not ai_suggestion.get('success'):
                return
            
            # Tạo thông báo
            from activities.models import Notification
            
            suggestion_text = ai_suggestion.get('suggestion', '')
            if suggestion_text:
                Notification.objects.create(
                    user=user,
                    title='💡 AI gợi ý cho bạn',
                    message=suggestion_text,
                    type='info',
                    category='ai_improvement',
                    metadata={
                        'score_percent': percent,
                        'wrong_count': len(wrong_answers),
                        'exercise_id': summary.get('exercise_id'),
                    }
                )
                logger.info(f"Sent improvement notification to user {user.id}")
                
        except Exception as e:
            logger.error(f"Error sending improvement notification: {e}")


class AttemptSummaryView(APIView):
    """
    GET /api/activities/attempts/{attempt_id}/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request, attempt_id: str):
        try:
            summary = get_attempt_summary(attempt_id)
        except NotFoundError:
            return Response({"detail": "Attempt not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(summary, status=status.HTTP_200_OK)