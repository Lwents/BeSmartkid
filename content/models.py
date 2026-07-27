import uuid
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator

# Create your models here.
class Subject(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)

    class Meta:
        verbose_name = ('Subject')
        verbose_name_plural = ('Subjects')
        ordering = ['title']

    def __str__(self):
        return self.title

class Course(models.Model):
    """Published courses are enrolled free; the platform has no purchase flow."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subject = models.ForeignKey(Subject, on_delete=models.SET_NULL, null=True, blank=True, related_name='courses')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    introduction = models.TextField(blank=True, null=True, help_text="Giới thiệu chi tiết về khóa học (hiển thị ở trang chi tiết)")
    grade = models.CharField(max_length=16, blank=True, null=True)
    created_on = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_on = models.DateTimeField(auto_now=True, null=True, blank=True)
    published = models.BooleanField(default=False)
    archived = models.BooleanField(default=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='courses_owned')
    video_url = models.URLField(blank=True, null=True, help_text="URL video khóa học (ví dụ: YouTube link hoặc link video trực tiếp)")
    video_file = models.FileField(upload_to='course_videos/', blank=True, null=True, help_text="File video khóa học (nếu không dùng URL)")
    thumbnail = models.ImageField(upload_to='course_thumbnails/', blank=True, null=True, help_text="Ảnh bìa khóa học")

    students = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through='Enrollment',
        related_name='enrolled_courses',
        blank=True
    )

    class Meta:
        verbose_name = ('Course')
        verbose_name_plural = ('Courses')
        ordering = ['title']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # An archived course must never remain visible through published queries.
        if self.archived:
            self.published = False
            update_fields = kwargs.get('update_fields')
            if update_fields is not None:
                kwargs['update_fields'] = set(update_fields) | {'published'}
        super().save(*args, **kwargs)

class Enrollment(models.Model):
    """Free learning access to a course, not a purchase or payment record."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='course_enrollments')
    enrolled_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('course', 'student')
        verbose_name = ('Enrollment')
        verbose_name_plural = ('Enrollments')
        ordering = ['-enrolled_at']
    
    def __str__(self):
        return f"{self.student} enrolled in {self.course}"

class Module(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='modules')
    title = models.CharField(max_length=255)
    position = models.IntegerField(default=0, validators=[MinValueValidator(0)])

    class Meta:
        verbose_name = ('Module')
        verbose_name_plural = ('Modules')
        ordering = ['position']

    def __str__(self):
        return f"{self.title} in {self.course}"

class Lesson(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='lessons')
    title = models.CharField(max_length=255)
    position = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    content_type = models.CharField(
        max_length=32,
        default='lesson',
        choices=[
            ('lesson', ('Lesson')),
            ('exploration', ('Exploration')),
            ('exercise', ('Exercise')),
            ('video', ('Video')),
            ('pdf', ('PDF')),
            ('text', ('Text')),
            ('document', ('Document')),
        ]
    )
    published = models.BooleanField(default=False)
    # Thêm các trường mới
    video_url = models.URLField(blank=True, null=True, help_text="URL video cho bài học")
    video_file = models.FileField(upload_to='lesson_videos/', blank=True, null=True, help_text="File video cho bài học")
    document_file = models.FileField(upload_to='lesson_documents/', blank=True, null=True, help_text="File tài liệu (PDF, DOCX)")
    text_content = models.TextField(blank=True, null=True, help_text="Nội dung văn bản")
    introduction = models.TextField(blank=True, null=True, help_text="Giới thiệu bài học (hiển thị trước video)")
    requires_exercise_completion = models.BooleanField(default=False, help_text="Yêu cầu hoàn thành bài tập trước khi tiếp tục")
    video_transcript = models.TextField(blank=True, null=True, help_text="Nội dung lời thoại/phụ đề video để AI hiểu ngữ cảnh")

    class Meta:
        verbose_name = ('Lesson')
        verbose_name_plural = ('Lessons')
        ordering = ['position']

    def __str__(self):
        return self.title

class LessonVersion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='versions')
    version = models.IntegerField(validators=[MinValueValidator(1)])
    status = models.CharField(
        max_length=32,
        default='draft',
        choices=[('draft', ('Draft')), ('review', ('Review')), ('published', ('Published'))]
    )
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='lesson_versions_authored')
    content = models.JSONField(default=dict, blank=True)  # Overall content structure
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('lesson', 'version')
        verbose_name = ('Lesson Version')
        verbose_name_plural = ('Lesson Versions')
        ordering = ['-version']

    def __str__(self):
        return f"{self.lesson} v{self.version}"

class ContentBlock(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lesson_version = models.ForeignKey(LessonVersion, on_delete=models.CASCADE, related_name='content_blocks')
    type = models.CharField(
        max_length=32,
        choices=[
            ('text', ('Text')), ('image', ('Image')), ('video', ('Video')),
            ('quiz', ('Quiz')), ('exploration_ref', ('Exploration Reference')),
            ('introduction', ('Introduction')), ('exercise_ref', ('Exercise Reference'))
        ]
    )
    position = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    payload = models.JSONField(default=dict)  # e.g., {'text': '...', 'audio_url': '...', 'tts_text': '...', 'captions_url': '...', 'exercise_id': '...'}

    class Meta:
        verbose_name = ('Content Block')
        verbose_name_plural = ('Content Blocks')
        ordering = ['position']

    def __str__(self):
        return f"{self.type} in {self.lesson_version}"

class LessonProgress(models.Model):
    """Track student progress through lessons - required for unlocking next lessons"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='progress_records')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='lesson_progress')
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    video_watched = models.BooleanField(default=False)
    exercise_completed = models.BooleanField(default=False)
    exercise_score = models.FloatField(null=True, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    last_accessed_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('lesson', 'student')
        verbose_name = ('Lesson Progress')
        verbose_name_plural = ('Lesson Progress')
        ordering = ['-last_accessed_at']
    
    def __str__(self):
        return f"{self.student} - {self.lesson} ({'Completed' if self.completed else 'In Progress'})"

class Exploration(models.Model):
    # Oppia-style: Interactive state-based lessons.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='explorations_owned')
    language = models.CharField(max_length=8, default='vi')
    published = models.BooleanField(default=False)

    class Meta:
        verbose_name = ('Exploration')
        verbose_name_plural = ('Explorations')

    def __str__(self):
        return self.title

class ExplorationState(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    exploration = models.ForeignKey(Exploration, on_delete=models.CASCADE, related_name='states')
    name = models.CharField(max_length=255)
    content = models.JSONField(default=dict)  # Prompt, text, media
    interaction = models.JSONField(default=dict)  # Input schema, hints

    class Meta:
        verbose_name = ('Exploration State')
        verbose_name_plural = ('Exploration States')

    def __str__(self):
        return f"{self.name} in {self.exploration}"

class ExplorationTransition(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    exploration = models.ForeignKey(Exploration, on_delete=models.CASCADE, related_name='transitions')
    from_state = models.ForeignKey(ExplorationState, on_delete=models.CASCADE, related_name='from_transitions')
    to_state = models.ForeignKey(ExplorationState, on_delete=models.CASCADE, related_name='to_transitions')
    condition = models.JSONField(default=dict)  # Rules, classifiers

    class Meta:
        verbose_name = ('Exploration Transition')
        verbose_name_plural = ('Exploration Transitions')

    def __str__(self):
        return f"From {self.from_state} to {self.to_state}"

class ContentLibrary(models.Model):
    """Reusable content items that can be added to courses"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    subject = models.CharField(
        max_length=32,
        choices=[
            ('math', 'Toán'),
            ('vietnamese', 'Tiếng Việt'),
            ('english', 'Tiếng Anh'),
            ('science', 'Khoa học'),
            ('history', 'Lịch sử')
        ],
        default='math'
    )
    type = models.CharField(
        max_length=32,
        choices=[
            ('video', 'Video'),
            ('pdf', 'PDF'),
            ('doc', 'Tài liệu'),
            ('quiz', 'Quiz'),
            ('text', 'Văn bản'),
            ('image', 'Hình ảnh')
        ],
        default='video'
    )
    grade_band = models.CharField(
        max_length=32,
        choices=[
            ('Khối 1', 'Khối 1'),
            ('Khối 2', 'Khối 2'),
            ('Khối 3', 'Khối 3'),
            ('Khối 4', 'Khối 4'),
            ('Khối 5', 'Khối 5'),
        ],
        default='Khối 1'
    )
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='content_library_items')
    meta = models.JSONField(default=dict, blank=True)  # duration, size, questions, etc.
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = ('Content Library Item')
        verbose_name_plural = ('Content Library Items')
        ordering = ['-updated_at']

    def __str__(self):
        return self.title
