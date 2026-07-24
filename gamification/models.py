import uuid
from django.db import models
from django.conf import settings as django_settings
from django.core.validators import MinValueValidator



# Create your models here.
class Badge(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField()
    icon_url = models.TextField(blank=True, null=True)
    criteria = models.JSONField(default=dict)  # e.g., {'complete_lessons': 10, 'min_score': 80}

    class Meta:
        verbose_name = ('Badge')
        verbose_name_plural = ('Badges')

    def __str__(self):
        return self.name

class UserBadge(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(django_settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='badges')
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE, related_name='user_badges')
    awarded_at = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict)  # e.g., {'reason': 'Completed course'}

    class Meta:
        unique_together = ('user', 'badge')
        verbose_name = ('User Badge')
        verbose_name_plural = ('User Badges')

    def __str__(self):
        return f"{self.badge} awarded to {self.user}"

class Reward(models.Model):
    # e.g., stars, points.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(django_settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='rewards')
    type = models.CharField(max_length=32, choices=[('star', ('Star')), ('point', ('Point')), ('level_up', ('Level Up'))])
    value = models.IntegerField(validators=[MinValueValidator(1)])
    awarded_at = models.DateTimeField(auto_now_add=True)
    source = models.CharField(max_length=128)  # e.g., 'lesson_complete'

    class Meta:
        verbose_name = ('Reward')
        verbose_name_plural = ('Rewards')
        ordering = ['-awarded_at']

    def __str__(self):
        return f"{self.value} {self.type} to {self.user}"


class Game(models.Model):
    """Educational games created by teachers"""
    GAME_TYPES = [
        ('quiz', 'Trắc nghiệm nhanh'),
        ('word_match', 'Ghép từ'),
        ('puzzle', 'Đố vui'),
        ('memory', 'Trí nhớ'),
        ('fill_blank', 'Điền từ'),
    ]
    
    DIFFICULTY_LEVELS = [
        ('easy', 'Dễ'),
        ('medium', 'Trung bình'),
        ('hard', 'Khó'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    game_type = models.CharField(max_length=32, choices=GAME_TYPES, default='quiz')
    difficulty = models.CharField(max_length=16, choices=DIFFICULTY_LEVELS, default='easy')
    
    # Content
    questions = models.JSONField(default=list)  # List of questions/items
    settings = models.JSONField(default=dict)  # Game-specific settings
    
    # Metadata
    created_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='created_games'
    )
    subject = models.CharField(max_length=64, blank=True)  # e.g., 'math', 'vietnamese', 'english'
    grade_level = models.PositiveIntegerField(null=True, blank=True)  # 1-5 for primary school
    
    # Status
    is_published = models.BooleanField(default=False)
    play_count = models.PositiveIntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Game'
        verbose_name_plural = 'Games'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title} ({self.get_game_type_display()})"


class GameSession(models.Model):
    """Track student game sessions and scores"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='sessions')
    player = models.ForeignKey(
        django_settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='game_sessions'
    )
    
    score = models.PositiveIntegerField(default=0)
    max_score = models.PositiveIntegerField(default=0)
    time_spent = models.PositiveIntegerField(default=0)  # seconds
    completed = models.BooleanField(default=False)
    
    answers = models.JSONField(default=list)  # Student's answers
    
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = 'Game Session'
        verbose_name_plural = 'Game Sessions'
        ordering = ['-started_at']
    
    def __str__(self):
        return f"{self.player} playing {self.game}"
