import uuid
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator

# Create your models here.
class Exercise(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lesson = models.ForeignKey('content.Lesson', on_delete=models.CASCADE, related_name='exercises', null=True, blank=True)
    title = models.CharField(max_length=255)
    type = models.CharField(
        max_length=32,
        choices=[('mcq', ('Multiple Choice')), ('short_answer', ('Short Answer')), ('matching', ('Matching'))]
    )
    published = models.BooleanField(default=False)  # Whether the exercise is published and visible to students

    class Meta:
        verbose_name = ('Exercise')
        verbose_name_plural = ('Exercises')

    def __str__(self):
        return self.title

class Question(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE, related_name='questions')
    prompt = models.TextField()
    meta = models.JSONField(default=dict)  # e.g., {'difficulty': 1-5, 'time_limit': 60, 'hints': [...]}

    class Meta:
        verbose_name = ('Question')
        verbose_name_plural = ('Questions')

    def __str__(self):
        return self.prompt[:50]

class Choice(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='choices')
    text = models.TextField()
    is_correct = models.BooleanField(default=False)
    position = models.IntegerField(default=0, validators=[MinValueValidator(0)])

    class Meta:
        verbose_name = ('Choice')
        verbose_name_plural = ('Choices')
        ordering = ['position']

    def __str__(self):
        return self.text[:50]

class ExerciseAttempt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE, related_name='attempts')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='exercise_attempts')
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    score = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(100)])
    metadata = models.JSONField(default=dict)  # e.g., {'time_taken': 300}

    class Meta:
        verbose_name = ('Exercise Attempt')
        verbose_name_plural = ('Exercise Attempts')

    def __str__(self):
        return f"Attempt for {self.exercise} by {self.student}"

class ExerciseAnswer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attempt = models.ForeignKey(ExerciseAttempt, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    answer = models.JSONField(default=dict)  # e.g., {'text': '...', 'selected_choice': 'uuid'}
    correct = models.BooleanField(null=True, blank=True)

    class Meta:
        verbose_name = ('Exercise Answer')
        verbose_name_plural = ('Exercise Answers')

    def __str__(self):
        return f"Answer for {self.question}"
    

class ExerciseSettings(models.Model):
    SHOW_ANSWERS_CHOICES = [
        ('always', 'Luôn hiển thị sau khi nộp bài'),
        ('after_duration', 'Chỉ hiển thị sau khi hết thời gian làm bài'),
        ('after_end', 'Chỉ hiển thị sau khi hết hạn bài thi'),
        ('never', 'Không hiển thị đáp án'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    exercise = models.OneToOneField('Exercise', on_delete=models.CASCADE, related_name='settings')
    time_limit_seconds = models.IntegerField(null=True, blank=True)  # None => no limit
    max_attempts = models.IntegerField(null=True, blank=True)  # None => unlimited
    shuffle_questions = models.BooleanField(default=True)
    shuffle_choices = models.BooleanField(default=True)
    pass_score = models.FloatField(default=50.0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    negative_marking = models.BooleanField(default=False)  # penalize wrong answers
    course_id = models.UUIDField(null=True, blank=True)  # Khóa học áp dụng (nếu là đề thi độc lập)
    show_answers = models.CharField(max_length=16, choices=SHOW_ANSWERS_CHOICES, default='always')
    scheduled_at = models.DateTimeField(null=True, blank=True)  # When to automatically publish
    end_at = models.DateTimeField(null=True, blank=True)  # When to automatically close the exam
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class Hint(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.ForeignKey('Question', on_delete=models.CASCADE, related_name='hints')
    text = models.TextField()
    order = models.IntegerField(default=0)

class Tag(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=64, unique=True)

class Skill(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=128, unique=True)

class QuestionStat(models.Model):
    question = models.OneToOneField('Question', on_delete=models.CASCADE, related_name='stats')
    times_shown = models.IntegerField(default=0)
    times_correct = models.IntegerField(default=0)
    average_time_seconds = models.FloatField(default=0.0)

class MatchingPair(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.ForeignKey('Question', on_delete=models.CASCADE, related_name='matching_pairs')
    left_text = models.TextField()
    right_text = models.TextField()
    correct_right_index = models.IntegerField()  # index into the right list to mark correct pairing

class FileUploadAnswer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attempt_answer = models.OneToOneField('ExerciseAnswer', on_delete=models.CASCADE, related_name='file_upload')
    file = models.FileField(upload_to='exercise_answers/')


# Teacher Feedback Model
class TeacherFeedback(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_feedbacks')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='received_feedbacks')
    course = models.ForeignKey('content.Course', on_delete=models.SET_NULL, null=True, blank=True, related_name='feedbacks')
    message = models.TextField()
    rating = models.FloatField(default=0.0, validators=[MinValueValidator(0), MaxValueValidator(10)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        verbose_name = ('Teacher Feedback')
        verbose_name_plural = ('Teacher Feedbacks')
        ordering = ['-created_at']

    def __str__(self):
        return f"Feedback from {self.teacher} to {self.student}"


# Notification Model
class Notification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=255)
    message = models.TextField()
    type = models.CharField(
        max_length=32,
        choices=[
            ('info', 'Info'),
            ('success', 'Success'),
            ('warning', 'Warning'),
            ('error', 'Error'),
        ],
        default='info'
    )
    category = models.CharField(max_length=64, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True)  # e.g., {'feedback_id': '...', 'course_id': '...'}

    class Meta:
        verbose_name = ('Notification')
        verbose_name_plural = ('Notifications')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} - {self.user}"


class NotificationLog(models.Model):
    """
    Track các notification đã gửi để tránh spam
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notification_logs')
    notification_type = models.CharField(
        max_length=64,
        choices=[
            ('streak_warning', 'Streak Warning'),
            ('comeback_1day', 'Come Back 1 Day'),
            ('comeback_3days', 'Come Back 3 Days'),
            ('comeback_7days', 'Come Back 7 Days'),
            ('comeback_email_1day', 'Come Back Email 1 Day'),
            ('comeback_email_3days', 'Come Back Email 3 Days'),
            ('comeback_email_7days', 'Come Back Email 7 Days'),
        ]
    )
    sent_at = models.DateTimeField(auto_now_add=True)
    sent_date = models.DateField(db_index=True)  # Ngày gửi (theo timezone local)
    metadata = models.JSONField(default=dict, blank=True)  # e.g., {'streak': 5, 'days_missed': 3}
    
    class Meta:
        verbose_name = ('Notification Log')
        verbose_name_plural = ('Notification Logs')
        ordering = ['-sent_at']
        indexes = [
            models.Index(fields=['user', 'notification_type', 'sent_date']),
            models.Index(fields=['user', '-sent_at']),
        ]
        unique_together = [('user', 'notification_type', 'sent_date')]  # Mỗi loại notification chỉ gửi 1 lần/ngày
    
    def __str__(self):
        return f"{self.user.username} - {self.notification_type} - {self.sent_date}"


class LessonQuestion(models.Model):
    """
    Câu hỏi của học sinh về một bài học. Giáo viên sẽ trả lời.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lesson = models.ForeignKey('content.Lesson', on_delete=models.CASCADE, related_name='questions')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='lesson_questions')
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Q by {self.student} on {self.lesson}"


class LessonQuestionReply(models.Model):
    """
    Trả lời cho câu hỏi, có thể từ giáo viên hoặc học sinh.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.ForeignKey(LessonQuestion, on_delete=models.CASCADE, related_name='replies')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='lesson_question_replies')
    content = models.TextField()
    is_teacher = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Reply by {self.user} on {self.question_id}"


class LessonQuestionReaction(models.Model):
    """
    Cảm xúc/like cho câu hỏi hoặc câu trả lời.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.ForeignKey('LessonQuestion', on_delete=models.CASCADE, related_name='reactions', null=True, blank=True)
    reply = models.ForeignKey(LessonQuestionReply, on_delete=models.CASCADE, related_name='reactions', null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='lesson_question_reactions')
    emoji = models.CharField(max_length=16, default='like')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        # Use database-level constraints
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(question__isnull=False, reply__isnull=True) |
                    models.Q(question__isnull=True, reply__isnull=False)
                ),
                name='lesson_question_reaction_must_have_question_or_reply'
            )
        ]

    def __str__(self):
        return f"{self.emoji} by {self.user} on {self.reply_id}"


class LessonQuestionReport(models.Model):
    """
    Báo cáo vi phạm cho câu hỏi hoặc trả lời.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='lesson_question_reports')
    question = models.ForeignKey(LessonQuestion, null=True, blank=True, on_delete=models.CASCADE, related_name='reports')
    reply = models.ForeignKey(LessonQuestionReply, null=True, blank=True, on_delete=models.CASCADE, related_name='reports')
    reason = models.CharField(max_length=255, blank=True)
    detail = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(question__isnull=False, reply__isnull=True) |
                    models.Q(question__isnull=True, reply__isnull=False)
                ),
                name='lesson_question_report_must_have_question_or_reply'
            )
        ]

    def __str__(self):
        target = self.question_id or self.reply_id
        return f"Report {target} by {self.reporter}"
