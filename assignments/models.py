# assignments/infrastructure/models.py
"""
Django ORM models for the assignments module.
These are thin persistence layers - all business logic lives in domain objects.
"""
import uuid
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.translation import gettext_lazy as _



class Assignment(models.Model):
    """
    Represents a homework/assessment assignment in the system.
    Teachers create assignments for students to complete.
    """
    
    class AssignmentType(models.TextChoices):
        HOMEWORK = 'homework', _('Homework')
        QUIZ = 'quiz', _('Quiz')
        PROJECT = 'project', _('Project')
        WORKSHEET = 'worksheet', _('Worksheet')
        ESSAY = 'essay', _('Essay')
    
    class Status(models.TextChoices):
        DRAFT = 'draft', _('Draft')
        PUBLISHED = 'published', _('Published')
        ARCHIVED = 'archived', _('Archived')
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Relationships
    classroom = models.ForeignKey(
        'school.ClassroomModel',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assignments',
        help_text=_("The classroom this assignment is assigned to")
    )
    lesson = models.ForeignKey(
        'content.Lesson',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assignments',
        help_text=_("The lesson this assignment is linked to")
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assignments_created',
        help_text=_("The teacher who created this assignment")
    )
    
    # Core fields
    title = models.CharField(max_length=255, db_index=True)
    description = models.TextField(blank=True)
    instructions = models.TextField(
        blank=True,
        help_text=_("Detailed instructions for students")
    )
    assignment_type = models.CharField(
        max_length=32,
        choices=AssignmentType.choices,
        default=AssignmentType.HOMEWORK
    )
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.DRAFT
    )
    
    # Grading configuration
    max_score = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal('100.00'),
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text=_("Maximum possible score")
    )
    passing_score = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text=_("Minimum score to pass")
    )
    
    # Timing
    due_date = models.DateTimeField(null=True,blank=True,db_index=True)
    available_from = models.DateTimeField(null=True,blank=True)
    available_until = models.DateTimeField(null=True,blank=True)
    
    # Settings
    allow_late_submissions = models.BooleanField(default=True)
    late_penalty_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))],
        help_text=_("Percentage penalty per day late")
    )
    max_attempts = models.PositiveIntegerField(
        default=1,
        help_text=_("Maximum number of submission attempts (0 = unlimited)")
    )
    is_group_assignment = models.BooleanField(
        default=False,
        help_text=_("Whether this is a group assignment")
    )
    auto_grade = models.BooleanField(
        default=False,
        help_text=_("Whether to automatically grade submissions")
    )

    # Child safety
    requires_parent_consent = models.BooleanField(default=False)
    age_appropriate_level = models.PositiveSmallIntegerField(default=1)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    
    class Meta:
        verbose_name = _('Assignment')
        verbose_name_plural = _('Assignments')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'due_date']),
            models.Index(fields=['classroom', 'status']),
            models.Index(fields=['teacher', 'created_at']),
        ]
    
    def __str__(self):
        return self.title


class Submission(models.Model):
    """Django ORM model for Submission."""
    
    class Status(models.TextChoices):
        DRAFT = 'draft', _('Draft')
        SUBMITTED = 'submitted', _('Submitted')
        GRADED = 'graded', _('Graded')
        RETURNED = 'returned', _('Returned')
        REJECTED = 'rejected', _('Rejected')
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name='submissions'
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='submissions'
    )
    # group = models.ForeignKey(
    #     'school.GroupModel',
    #     on_delete=models.SET_NULL,
    #     null=True,
    #     blank=True,
    #     related_name='submissions'
    # )
    
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True
    )
    content = models.TextField(blank=True)
    attempt_number = models.PositiveIntegerField(default=1)
    
    submitted_at = models.DateTimeField(null=True, blank=True)
    is_late = models.BooleanField(default=False)
    late_days = models.PositiveIntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    version = models.PositiveIntegerField(default=1)
    
    class Meta:
        db_table = 'assignment_submissions'
        ordering = ['-created_at']
        unique_together = [['assignment', 'student', 'attempt_number']]
        indexes = [
            models.Index(fields=['assignment', 'status']),
            models.Index(fields=['student', 'status']),
        ]
    
    def __str__(self):
        return f"{self.student} - {self.assignment.title} (Attempt {self.attempt_number})"


class Grade(models.Model):
    """Django ORM model for Grade."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    submission = models.OneToOneField(
        Submission,
        on_delete=models.CASCADE,
        related_name='grade'
    )
    grader = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='grades_given'
    )
    
    raw_score = models.DecimalField(max_digits=6, decimal_places=2)
    max_score = models.DecimalField(max_digits=6, decimal_places=2)
    late_penalty_applied = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00')
    )
    final_score = models.DecimalField(max_digits=6, decimal_places=2)
    percentage = models.DecimalField(max_digits=5, decimal_places=2)
    letter_grade = models.CharField(max_length=5, blank=True)
    
    feedback = models.TextField(blank=True)
    is_final = models.BooleanField(default=True)
    
    graded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'assignment_grades'
        ordering = ['-graded_at']
    
    def __str__(self):
        return f"Grade for {self.submission}"