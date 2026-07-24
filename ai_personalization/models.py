# import uuid
# from django.db import models
# from django.conf import settings
# from django.utils import timezone
# from django.core.validators import MinValueValidator, MaxValueValidator



# # Create your models here.
# class LearningPath(models.Model):
#     id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
#     student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='learning_paths')
#     course = models.ForeignKey('content.Course', on_delete=models.CASCADE, related_name='learning_paths')
#     path = models.JSONField(default=list)  # e.g., [{'lesson_id': 'uuid', 'order': 1}, ...]
#     generated_at = models.DateTimeField(auto_now_add=True)
#     ai_model = models.CharField(max_length=128, blank=True, null=True)  # e.g., 'gpt-4'
#     metadata = models.JSONField(default=dict)  # e.g., {'based_on': 'weak_points'}

#     class Meta:
#         unique_together = ('student', 'course')
#         verbose_name = ('Learning Path')
#         verbose_name_plural = ('Learning Paths')

#     def __str__(self):
#         return f"Path for {self.course} by {self.student}"


# class Recommendation(models.Model):
#     id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
#     student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='recommendations')
#     recommended_lesson = models.ForeignKey('content.Lesson', on_delete=models.CASCADE, related_name='recommendations')
#     score = models.FloatField(validators=[MinValueValidator(0), MaxValueValidator(1)])
#     reason = models.TextField()
#     generated_at = models.DateTimeField(auto_now_add=True)

#     class Meta:
#         verbose_name = ('Recommendation')
#         verbose_name_plural = ('Recommendations')
#         ordering = ['-score']

#     def __str__(self):
#         return f"Recommend {self.recommended_lesson} to {self.student}"
    

# class LearningEvent(models.Model):
#     """Event log from frontend — minimal schema to start."""
#     id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
#     user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='learning_events')
#     course = models.ForeignKey('content.Course', on_delete=models.CASCADE, null=True, blank=True)
#     lesson = models.ForeignKey('content.Lesson', on_delete=models.CASCADE, null=True, blank=True)
#     timestamp = models.DateTimeField(default=timezone.now)
#     event_type = models.CharField(max_length=64)  # e.g., 'start', 'submit', 'hint', 'skip', 'complete'
#     detail = models.JSONField(default=dict)  # e.g., {'correct': True, 'attempts': 2, 'time_spent': 45}
#     session_id = models.UUIDField(null=True, blank=True)

#     class Meta:
#         indexes = [
#             models.Index(fields=['user', 'timestamp']),
#             models.Index(fields=['lesson']),
#         ]


# class ContentSkill(models.Model):
#     """Map content/lesson -> skill tag(s)."""
#     id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
#     lesson = models.ForeignKey('content.Lesson', on_delete=models.CASCADE, related_name='content_skills')
#     skill = models.CharField(max_length=128)  # e.g., 'fractions:add'
#     weight = models.FloatField(default=1.0)   # optional: weight of skill in lesson

#     class Meta:
#         unique_together = ('lesson', 'skill')


# class UserSkillMastery(models.Model):
#     """Track estimated mastery for a user on each skill (0..1)."""
#     user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='skill_masteries')
#     skill = models.CharField(max_length=128)
#     mastery = models.FloatField(default=0.0, validators=[MinValueValidator(0.0), MaxValueValidator(1.0)])
#     last_update = models.DateTimeField(auto_now=True)

#     class Meta:
#         unique_together = ('user', 'skill')
#         indexes = [models.Index(fields=['user', 'skill'])]


# class RecommendationLog(models.Model):
#     id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
#     user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='recommendation_logs')
#     lesson = models.ForeignKey('content.Lesson', on_delete=models.CASCADE)
#     score = models.FloatField(validators=[MinValueValidator(0), MaxValueValidator(1)])
#     reason = models.TextField(blank=True)
#     source = models.CharField(max_length=32, default='rule')  # 'rule', 'model', 'manual'
#     shown_at = models.DateTimeField(auto_now_add=True)
#     acted_at = models.DateTimeField(null=True, blank=True)  # when user clicked/started
#     accepted = models.BooleanField(null=True)  # user accepted (started/completed)
#     feedback = models.JSONField(default=dict)  # e.g., {'outcome': 'correct', 'attempts': 2}

#     class Meta:
#         ordering = ['-shown_at']
    


# ai_personalization/models.py
"""
Enhanced models for AI-driven personalization in eLearning platform.
Implements Domain-Driven Design patterns with inspiration from Duolingo's HLR,
Khan Academy's mastery system, and Oppia's adaptive learning.
"""
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from typing import Dict, List, Optional
import uuid
import logging

logger = logging.getLogger(__name__)


class LearningPathManager(models.Manager):
    """Custom manager for LearningPath with domain logic."""
    
    def get_active_path(self, student, course):
        """Get the most recent active learning path for a student."""
        return self.filter(
            student=student,
            course=course
        ).order_by('-generated_at').first()
    
    def create_path(self, student, course, path_data: List[Dict], ai_model: str = None, metadata: Dict = None):
        """Create a new learning path with validation."""
        if not path_data:
            raise ValidationError("Path data cannot be empty")
        
        # Validate path structure
        for step in path_data:
            if 'lesson_id' not in step or 'order' not in step:
                raise ValidationError("Each path step must have 'lesson_id' and 'order'")
        
        return self.create(
            student=student,
            course=course,
            path=path_data,
            ai_model=ai_model or 'rule-based',
            metadata=metadata or {}
        )


class LearningPath(models.Model):
    """
    Personalized learning sequence for a student in a specific course.
    Inspired by Duolingo's adaptive skill trees and Khan Academy's mastery paths.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='learning_paths'
    )
    course = models.ForeignKey(
        'content.Course',
        on_delete=models.CASCADE,
        related_name='learning_paths'
    )
    path = models.JSONField(
        default=list,
        help_text="Ordered list of lesson steps with metadata"
    )
    generated_at = models.DateTimeField(auto_now_add=True, db_index=True)
    ai_model = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        help_text="AI model used for generation (e.g., 'gpt-4', 'hlr-v1')"
    )
    metadata = models.JSONField(
        default=dict,
        help_text="Additional context like weak_skills, difficulty_level"
    )
    
    objects = LearningPathManager()
    
    class Meta:
        unique_together = ('student', 'course')
        verbose_name = 'Learning Path'
        verbose_name_plural = 'Learning Paths'
        indexes = [
            models.Index(fields=['student', 'course', '-generated_at']),
        ]
    
    def __str__(self):
        return f"Path for {self.student.username} in {self.course.title}"
    
    def get_next_lesson(self) -> Optional[Dict]:
        """Get the next unvisited lesson in the path."""
        if not self.path:
            return None
        # Implementation would check LearningEvent for completed lessons
        return self.path[0] if self.path else None
    
    def update_path(self, new_path: List[Dict], metadata: Dict = None):
        """Update path with new ordering (e.g., after skill mastery change)."""
        self.path = new_path
        if metadata:
            self.metadata.update(metadata)
        self.generated_at = timezone.now()
        self.save(update_fields=['path', 'metadata', 'generated_at'])


class RecommendationManager(models.Manager):
    """Custom manager for Recommendations."""
    
    def get_top_recommendations(self, student, limit: int = 5):
        """Get top N recommendations for a student, ordered by score."""
        return self.filter(
            student=student,
            generated_at__gte=timezone.now() - timezone.timedelta(days=7)
        ).order_by('-score')[:limit]
    
    def create_recommendation(self, student, lesson, score: float, reason: str):
        """Create a recommendation with validation."""
        if not 0 <= score <= 1:
            raise ValidationError("Score must be between 0 and 1")
        
        return self.create(
            student=student,
            recommended_lesson=lesson,
            score=score,
            reason=reason
        )


class Recommendation(models.Model):
    """
    AI-generated lesson recommendation for a student.
    Uses collaborative filtering + content-based approach.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='recommendations'
    )
    recommended_lesson = models.ForeignKey(
        'content.Lesson',
        on_delete=models.CASCADE,
        related_name='recommendations'
    )
    score = models.FloatField(
        validators=[MinValueValidator(0), MaxValueValidator(1)],
        help_text="Recommendation confidence score (0-1)"
    )
    reason = models.TextField(help_text="Human-readable explanation")
    generated_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    objects = RecommendationManager()
    
    class Meta:
        verbose_name = 'Recommendation'
        verbose_name_plural = 'Recommendations'
        ordering = ['-score', '-generated_at']
        indexes = [
            models.Index(fields=['student', '-score']),
            models.Index(fields=['-generated_at']),
        ]
    
    def __str__(self):
        return f"Recommend {self.recommended_lesson.title} to {self.student.username} ({self.score:.2f})"


class LearningEventManager(models.Manager):
    """Custom manager for learning events with analytics queries."""
    
    def recent_events(self, user, days: int = 7):
        """Get recent events for a user."""
        since = timezone.now() - timezone.timedelta(days=days)
        return self.filter(user=user, timestamp__gte=since).order_by('-timestamp')
    
    def events_by_lesson(self, lesson, days: int = 30):
        """Get all events for a lesson in the last N days."""
        since = timezone.now() - timezone.timedelta(days=days)
        return self.filter(lesson=lesson, timestamp__gte=since)
    
    def success_rate(self, user, lesson) -> Optional[float]:
        """Calculate success rate for a user on a specific lesson."""
        events = self.filter(
            user=user,
            lesson=lesson,
            event_type__in=['submit', 'complete']
        )
        if not events.exists():
            return None
        
        successful = events.filter(
            detail__correct=True
        ).count()
        total = events.count()
        return successful / total if total > 0 else 0.0


class LearningEvent(models.Model):
    """
    Event sourcing for all learner interactions.
    Minimal schema for high-throughput write operations.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='learning_events',
        db_index=True
    )
    course = models.ForeignKey(
        'content.Course',
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    lesson = models.ForeignKey(
        'content.Lesson',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_index=True
    )
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    event_type = models.CharField(
        max_length=64,
        choices=[
            ('start', 'Started'),
            ('submit', 'Submitted Answer'),
            ('hint', 'Used Hint'),
            ('skip', 'Skipped'),
            ('complete', 'Completed'),
            ('pause', 'Paused'),
            ('resume', 'Resumed'),
        ],
        db_index=True
    )
    detail = models.JSONField(
        default=dict,
        help_text="Event metadata: correct, attempts, time_spent, etc."
    )
    session_id = models.UUIDField(null=True, blank=True, db_index=True)
    
    objects = LearningEventManager()
    
    class Meta:
        indexes = [
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['lesson', 'timestamp']),
            models.Index(fields=['session_id']),
            models.Index(fields=['event_type', 'timestamp']),
        ]
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.user.username} - {self.event_type} - {self.timestamp}"
    
    @property
    def is_successful(self) -> bool:
        """Check if this event represents successful completion."""
        return self.detail.get('correct', False) or self.event_type == 'complete'


class ContentSkillManager(models.Manager):
    """Manager for content-skill mappings."""
    
    def skills_for_lesson(self, lesson) -> List[str]:
        """Get all skills taught in a lesson."""
        return list(
            self.filter(lesson=lesson).values_list('skill', flat=True)
        )
    
    def lessons_for_skill(self, skill: str):
        """Get all lessons that teach a specific skill."""
        return self.filter(skill=skill).select_related('lesson')


class ContentSkill(models.Model):
    """
    Many-to-many mapping between content (lessons) and skills.
    Enables skill-based recommendations and mastery tracking.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lesson = models.ForeignKey(
        'content.Lesson',
        on_delete=models.CASCADE,
        related_name='content_skills'
    )
    skill = models.CharField(
        max_length=128,
        db_index=True,
        help_text="Skill identifier (e.g., 'math:fractions:add')"
    )
    weight = models.FloatField(
        default=1.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Importance of skill in this lesson (0-1)"
    )
    
    objects = ContentSkillManager()
    
    class Meta:
        unique_together = ('lesson', 'skill')
        indexes = [
            models.Index(fields=['skill']),
            models.Index(fields=['lesson', 'skill']),
        ]
    
    def __str__(self):
        return f"{self.lesson.title} -> {self.skill} ({self.weight})"


class UserSkillMasteryManager(models.Manager):
    """Manager for skill mastery with Bayesian updates."""
    
    def get_mastery(self, user, skill: str) -> float:
        """Get current mastery level for a skill (0-1)."""
        obj = self.filter(user=user, skill=skill).first()
        return obj.mastery if obj else 0.0
    
    def update_mastery(self, user, skill: str, delta: float):
        """Update mastery using Bayesian approach."""
        obj, created = self.get_or_create(
            user=user,
            skill=skill,
            defaults={'mastery': 0.0}
        )
        
        # Bayesian update: new_mastery = old + delta * (1 - old)
        # This ensures mastery stays in [0, 1] and converges
        new_mastery = obj.mastery + delta * (1.0 - obj.mastery) if delta > 0 else max(0, obj.mastery + delta)
        obj.mastery = max(0.0, min(1.0, new_mastery))
        obj.save(update_fields=['mastery', 'last_update'])
        
        return obj.mastery
    
    def weak_skills(self, user, threshold: float = 0.5, limit: int = 10):
        """Get user's weakest skills below threshold."""
        return self.filter(
            user=user,
            mastery__lt=threshold
        ).order_by('mastery')[:limit]


class UserSkillMastery(models.Model):
    """
    Track estimated mastery for each user-skill pair.
    Implements Half-Life Regression inspired by Duolingo.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='skill_masteries'
    )
    skill = models.CharField(max_length=128, db_index=True)
    mastery = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Estimated mastery level (0=none, 1=mastered)"
    )
    last_update = models.DateTimeField(auto_now=True, db_index=True)
    
    # Half-Life Regression parameters (inspired by Duolingo)
    half_life_days = models.FloatField(
        default=1.0,
        help_text="Half-life in days for memory decay"
    )
    practice_count = models.IntegerField(default=0)
    correct_count = models.IntegerField(default=0)
    
    objects = UserSkillMasteryManager()
    
    class Meta:
        unique_together = ('user', 'skill')
        verbose_name = 'User Skill Mastery'
        verbose_name_plural = 'User Skill Masteries'
        indexes = [
            models.Index(fields=['user', 'skill']),
            models.Index(fields=['user', 'mastery']),
            models.Index(fields=['-last_update']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.skill}: {self.mastery:.2f}"
    
    def calculate_recall_probability(self) -> float:
        """
        Calculate current recall probability using HLR formula.
        p = 2^(-Δ/h) where Δ is time since last update, h is half-life.
        """
        delta_days = (timezone.now() - self.last_update).total_seconds() / 86400
        recall_prob = 2 ** (-delta_days / self.half_life_days)
        return max(0.0, min(1.0, recall_prob))
    
    def update_from_event(self, correct: bool, time_spent: float = 0):
        """Update mastery based on practice event."""
        self.practice_count += 1
        if correct:
            self.correct_count += 1
        
        # Update mastery using exponential moving average
        alpha = 0.3  # Learning rate
        observation = 1.0 if correct else 0.0
        self.mastery = alpha * observation + (1 - alpha) * self.mastery
        
        # Update half-life (doubles on success, halves on failure)
        if correct:
            self.half_life_days = min(90, self.half_life_days * 1.5)
        else:
            self.half_life_days = max(0.5, self.half_life_days * 0.7)
        
        self.save(update_fields=['mastery', 'half_life_days', 'practice_count', 'correct_count', 'last_update'])


class RecommendationLog(models.Model):
    """
    Audit trail for recommendations shown to users.
    Enables A/B testing and recommendation performance tracking.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='recommendation_logs'
    )
    lesson = models.ForeignKey('content.Lesson', on_delete=models.CASCADE)
    score = models.FloatField(
        validators=[MinValueValidator(0), MaxValueValidator(1)]
    )
    reason = models.TextField(blank=True)
    source = models.CharField(
        max_length=32,
        default='rule',
        choices=[
            ('rule', 'Rule-based'),
            ('model', 'ML Model'),
            ('manual', 'Manual Override'),
            ('collaborative', 'Collaborative Filtering'),
            ('content', 'Content-based'),
        ]
    )
    shown_at = models.DateTimeField(auto_now_add=True, db_index=True)
    acted_at = models.DateTimeField(null=True, blank=True)
    accepted = models.BooleanField(null=True)
    feedback = models.JSONField(
        default=dict,
        help_text="Outcome data: correct, attempts, time_spent"
    )
    
    class Meta:
        ordering = ['-shown_at']
        indexes = [
            models.Index(fields=['user', '-shown_at']),
            models.Index(fields=['source', '-shown_at']),
            models.Index(fields=['accepted']),
        ]
    
    def __str__(self):
        status = "Accepted" if self.accepted else "Shown"
        return f"{status}: {self.lesson.title} to {self.user.username}"
    
    def mark_accepted(self):
        """Mark recommendation as accepted when user starts the lesson."""
        self.acted_at = timezone.now()
        self.accepted = True
        self.save(update_fields=['acted_at', 'accepted'])


# Additional models based on research insights

class SkillPrerequisite(models.Model):
    """
    Graph structure for skill dependencies.
    Inspired by Khan Academy's knowledge map.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    skill = models.CharField(max_length=128, db_index=True)
    prerequisite_skill = models.CharField(max_length=128, db_index=True)
    strength = models.FloatField(
        default=1.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Strength of prerequisite relationship (0=weak, 1=strong)"
    )
    
    class Meta:
        unique_together = ('skill', 'prerequisite_skill')
        indexes = [
            models.Index(fields=['skill']),
            models.Index(fields=['prerequisite_skill']),
        ]
    
    def __str__(self):
        return f"{self.skill} requires {self.prerequisite_skill}"


class PersonalizationRule(models.Model):
    """
    Rule-based personalization for cold-start and fallback scenarios.
    Provides explainable recommendations when ML models have insufficient data.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=128, unique=True)
    description = models.TextField()
    condition = models.JSONField(
        help_text="Rule conditions as JSON (e.g., {'mastery_below': 0.5})"
    )
    action = models.JSONField(
        help_text="Action to take (e.g., {'recommend_skill': 'fractions:basics'})"
    )
    priority = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-priority', 'name']
    
    def __str__(self):
        return f"Rule: {self.name}"


class MLModelVersion(models.Model):
    """
    Track ML model versions for A/B testing and rollback.
    Essential for production ML systems.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=128)
    version = models.CharField(max_length=32)
    model_type = models.CharField(
        max_length=64,
        choices=[
            ('hlr', 'Half-Life Regression'),
            ('collaborative', 'Collaborative Filtering'),
            ('content_based', 'Content-Based'),
            ('neural', 'Neural Network'),
        ]
    )
    parameters = models.JSONField(default=dict)
    metrics = models.JSONField(
        default=dict,
        help_text="Performance metrics: MAE, AUC, precision, recall"
    )
    is_active = models.BooleanField(default=False)
    deployed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('name', 'version')
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} v{self.version}"


class UserProfile(models.Model):
    """
    Extended user profile for collaborative filtering.
    Stores demographics and learning preferences.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='personalization_profile'
    )
    age_group = models.CharField(
        max_length=32,
        choices=[
            ('6-8', '6-8 years'),
            ('9-11', '9-11 years'),
            ('12-14', '12-14 years'),
        ],
        null=True,
        blank=True
    )
    learning_style = models.CharField(
        max_length=32,
        choices=[
            ('visual', 'Visual'),
            ('auditory', 'Auditory'),
            ('kinesthetic', 'Kinesthetic'),
            ('mixed', 'Mixed'),
        ],
        default='mixed'
    )
    difficulty_preference = models.CharField(
        max_length=32,
        choices=[
            ('easy', 'Easy'),
            ('medium', 'Medium'),
            ('hard', 'Hard'),
            ('adaptive', 'Adaptive'),
        ],
        default='adaptive'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Profile: {self.user.username}"


class StreakRestoration(models.Model):
    """
    Track streak restorations - cho phép khôi phục streak tối đa 2 lần/tháng
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='streak_restorations',
        db_index=True
    )
    restored_at = models.DateTimeField(default=timezone.now, db_index=True)
    month_year = models.CharField(
        max_length=7,
        help_text="Format: YYYY-MM (e.g., 2025-12)",
        db_index=True
    )
    restored_streak_value = models.IntegerField(
        default=0,
        help_text="Giá trị streak đã được khôi phục"
    )
    
    class Meta:
        verbose_name = 'Streak Restoration'
        verbose_name_plural = 'Streak Restorations'
        ordering = ['-restored_at']
        indexes = [
            models.Index(fields=['user', 'month_year']),
            models.Index(fields=['user', '-restored_at']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.month_year} - {self.restored_at.date()}"
    
    @classmethod
    def get_restoration_count_this_month(cls, user):
        """Đếm số lần đã khôi phục trong tháng hiện tại"""
        today = timezone.localdate()
        month_year = today.strftime('%Y-%m')
        return cls.objects.filter(user=user, month_year=month_year).count()
    
    @classmethod
    def can_restore(cls, user):
        """Kiểm tra xem user có thể khôi phục streak không (tối đa 2 lần/tháng)"""
        return cls.get_restoration_count_this_month(user) < 2

