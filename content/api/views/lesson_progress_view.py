# content/api/views/lesson_progress_view.py
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils import timezone

from content import models
from activities.models import ExerciseAttempt


class LessonProgressView(APIView):
    """
    GET /api/lessons/{lesson_id}/progress/ - Get progress for current user
    POST /api/lessons/{lesson_id}/progress/ - Update progress (mark video watched, exercise completed, etc.)
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, lesson_id):
        """Get progress for current user"""
        lesson = get_object_or_404(models.Lesson, id=lesson_id)
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
        lesson = get_object_or_404(models.Lesson, id=lesson_id)
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
    GET /api/lessons/{lesson_id}/unlock-check/ - Check if lesson can be unlocked
    Logic: 
    1. Tất cả bài học trong module trước phải hoàn thành
    2. Bài học trước trong cùng module phải hoàn thành
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, lesson_id):
        """Check if lesson can be unlocked"""
        lesson = get_object_or_404(models.Lesson, id=lesson_id)
        student = request.user
        
        can_unlock = True
        reason = None
        
        # 1. Check module trước (chương trước) - phải hoàn thành HẾT
        current_module = lesson.module
        previous_module = models.Module.objects.filter(
            course=current_module.course,
            position__lt=current_module.position
        ).order_by('-position').first()
        
        if previous_module:
            # Đếm số bài học đã hoàn thành trong module trước
            total_lessons_in_prev = models.Lesson.objects.filter(
                module=previous_module,
                published=True
            ).count()
            
            completed_lessons_in_prev = models.LessonProgress.objects.filter(
                lesson__module=previous_module,
                student=student,
                completed=True
            ).count()
            
            if total_lessons_in_prev > 0 and completed_lessons_in_prev < total_lessons_in_prev:
                can_unlock = False
                reason = f"Bạn cần hoàn thành tất cả bài học trong {previous_module.title} trước khi xem {current_module.title}"
        
        # 2. Check bài học trước trong cùng module
        if can_unlock:
            previous_lesson = models.Lesson.objects.filter(
                module=lesson.module,
                position__lt=lesson.position,
                published=True
            ).order_by('-position').first()
        
        if previous_lesson:
            prev_progress = models.LessonProgress.objects.filter(
                lesson=previous_lesson,
                    student=student
            ).first()
            
            if not prev_progress or not prev_progress.completed:
                can_unlock = False
                reason = f"Bạn cần hoàn thành bài học trước: {previous_lesson.title}"
        
        return Response({
            'can_unlock': can_unlock,
            'reason': reason,
            'previous_lesson_id': str(previous_lesson.id) if 'previous_lesson' in locals() and previous_lesson else None
        })








