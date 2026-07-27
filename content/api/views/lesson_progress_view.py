# content/api/views/lesson_progress_view.py
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils import timezone

from content import models
from activities.models import ExerciseAttempt
from content.services.lesson_access_service import get_lesson_unlock_status


def _is_enrolled_student(user, lesson):
    return bool(
        getattr(user, "role", "") == "student"
        and lesson.published
        and lesson.module.course.published
        and models.Enrollment.objects.filter(
            course=lesson.module.course,
            student=user,
        ).exists()
    )


class LessonProgressView(APIView):
    """
    GET /api/lessons/{lesson_id}/progress/ - Get progress for current user
    POST /api/lessons/{lesson_id}/progress/ - Update progress (mark video watched, exercise completed, etc.)
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, lesson_id):
        """Get progress for current user"""
        lesson = get_object_or_404(
            models.Lesson.objects.select_related("module__course"), id=lesson_id
        )
        if not _is_enrolled_student(request.user, lesson):
            return Response(
                {"detail": "Bạn chưa tham gia khóa học này."},
                status=status.HTTP_403_FORBIDDEN,
            )
        progress, created = models.LessonProgress.objects.get_or_create(
            lesson=lesson,
            student=request.user,
            defaults={'completed': False}
        )
        return Response({
            'completed': progress.completed,
            'video_watched': progress.video_watched,
            'exercise_completed': progress.exercise_completed,
            'exercise_score': progress.exercise_score,
            'started_at': progress.started_at,
            'last_accessed_at': progress.last_accessed_at
        })

    def post(self, request, lesson_id):
        """Update progress"""
        lesson = get_object_or_404(
            models.Lesson.objects.select_related("module__course"), id=lesson_id
        )
        if not _is_enrolled_student(request.user, lesson):
            return Response(
                {"detail": "Bạn chưa tham gia khóa học này."},
                status=status.HTTP_403_FORBIDDEN,
            )
        unlock_status = get_lesson_unlock_status(lesson, request.user)
        if not unlock_status.can_unlock:
            return Response({
                'detail': unlock_status.reason,
                'can_unlock': False,
            }, status=status.HTTP_403_FORBIDDEN)

        progress, created = models.LessonProgress.objects.get_or_create(
            lesson=lesson,
            student=request.user,
            defaults={'completed': False}
        )
        
        # Update fields from request
        if 'video_watched' in request.data:
            progress.video_watched = bool(request.data['video_watched'])
        
        if 'exercise_completed' in request.data:
            progress.exercise_completed = bool(request.data['exercise_completed'])
            if 'exercise_score' in request.data:
                progress.exercise_score = float(request.data['exercise_score'])

        if 'completed' in request.data:
            progress.completed = bool(request.data['completed'])
            if progress.completed and not progress.completed_at:
                progress.completed_at = timezone.now()
        
        # Mark as completed if all requirements met
        if progress.video_watched and not progress.completed:
            if not lesson.requires_exercise_completion or progress.exercise_completed:
                progress.completed = True
                progress.completed_at = timezone.now()
        
        # Đảm bảo last_accessed_at được cập nhật (dù auto_now=True, vẫn set rõ ràng)
        progress.last_accessed_at = timezone.now()
        progress.save(update_fields=[
            'video_watched', 'exercise_completed', 'exercise_score',
            'completed', 'completed_at', 'last_accessed_at'
        ])
        
        return Response({
            'completed': progress.completed,
            'video_watched': progress.video_watched,
            'exercise_completed': progress.exercise_completed,
            'exercise_score': progress.exercise_score
        })


class LessonUnlockCheckView(APIView):
    """
    GET /api/content/lessons/{lesson_id}/unlock-check/
    Mọi bài đã xuất bản đứng trước bài hiện tại đều phải hoàn thành.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, lesson_id):
        """Check if lesson can be unlocked"""
        lesson = get_object_or_404(
            models.Lesson.objects.select_related('module', 'module__course'),
            id=lesson_id,
            published=True,
        )
        if not _is_enrolled_student(request.user, lesson):
            return Response(
                {"detail": "Bạn chưa tham gia khóa học này.", "can_unlock": False},
                status=status.HTTP_403_FORBIDDEN,
            )
        unlock_status = get_lesson_unlock_status(lesson, request.user)
        
        return Response({
            'can_unlock': unlock_status.can_unlock,
            'reason': unlock_status.reason,
            'previous_lesson_id': (
                str(unlock_status.blocking_lesson.id)
                if unlock_status.blocking_lesson else None
            ),
        })
