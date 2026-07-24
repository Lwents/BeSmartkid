
import uuid
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator

from content.models import Course, Lesson

class UserProgress(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='progress')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='progress')
    completed_lessons = models.PositiveIntegerField(default=0)
    total_lessons = models.PositiveIntegerField(default=0)
    progress_percentage = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    started_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('user', 'course')
        verbose_name = ("User Progress")
        verbose_name_plural = ("User Progresses")
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.user}'s progress in {self.course}"

class UserLessonProgress(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_progress = models.ForeignKey(UserProgress, on_delete=models.CASCADE, related_name='lesson_progress')
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='user_progress')
    status = models.CharField(
        max_length=20,
        choices=[('not_started', 'Not Started'), ('in_progress', 'In Progress'), ('completed', 'Completed')],
        default='not_started'
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('user_progress', 'lesson')
        verbose_name = ("User Lesson Progress")
        verbose_name_plural = ("User Lesson Progresses")
        ordering = ['lesson__position']

    def __str__(self):
        return f"{self.user_progress.user}'s progress on {self.lesson}"
