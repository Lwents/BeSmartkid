# content/serializers.py
from typing import Any, Dict, List, Optional
from django.contrib.auth import get_user_model
from rest_framework import serializers

from content import models
from content.domains.subject_domain import SubjectDomain
from content.domains.course_domain import CourseDomain
from content.domains.module_domain import ModuleDomain
from content.domains.lesson_domain import LessonDomain
from content.domains.lesson_version_domain import LessonVersionDomain
from content.domains.content_block_domain import ContentBlockDomain
from content.domains.exploration_domain import ExplorationDomain, ExplorationTransitionDomain, ExplorationStateDomain
User = get_user_model()


# -----------------------
# Helpers
# -----------------------
def _maybe_pk_to_id(obj):
    """If obj is a model instance or a pk, return string id or None."""
    if obj is None:
        return None
    if hasattr(obj, "id"):
        return str(obj.id)
    return str(obj)


# -----------------------
# Model Serializers (read/write that map Model <-> Domain)
# -----------------------

class SubjectSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    title = serializers.CharField(max_length=255)
    slug = serializers.SlugField(max_length=255)

    class Meta:
        model = models.Subject
        fields = ["id", "title", "slug"]
        read_only_fields = ["id"]

    def to_domain(self) -> SubjectDomain:
        """
        Convert serializer validated_data -> SubjectDomain.
        Caller should call is_valid() before.
        """
        data = self.validated_data
        domain = SubjectDomain(title=data["title"], slug=data["slug"])
        domain.validate()
        return domain

    @staticmethod
    def from_domain(domain: SubjectDomain) -> Dict[str, Any]:
        """Convert SubjectDomain -> primitive dict for API response."""
        return domain.to_dict()


class CourseSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    subject = serializers.PrimaryKeyRelatedField(queryset=models.Subject.objects.all(), allow_null=True, required=False)
    subject_slug = serializers.CharField(write_only=True, required=False, allow_null=True, allow_blank=True)
    subject_title = serializers.CharField(source="subject.title", read_only=True)
    owner = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), allow_null=True, required=False)
    title = serializers.CharField(max_length=255)
    description = serializers.CharField(allow_blank=True, required=False)
    introduction = serializers.CharField(allow_blank=True, required=False, help_text="Giới thiệu chi tiết về khóa học")
    grade = serializers.CharField(max_length=16, allow_blank=True, required=False)
    slug = serializers.SlugField(max_length=255, required=False, allow_null=True)
    published = serializers.BooleanField(default=False)
    published_at = serializers.DateTimeField(read_only=True)
    created_on = serializers.DateTimeField(read_only=True)
    updated_on = serializers.DateTimeField(read_only=True)
    createdAt = serializers.SerializerMethodField()
    updatedAt = serializers.SerializerMethodField()
    # Status field: computed from published boolean
    # 'draft' = not published, 'published' = published, 'archived' = not published (can be extended later)
    status = serializers.SerializerMethodField()
    enrollments = serializers.SerializerMethodField()
    lessonsCount = serializers.SerializerMethodField()
    video_url = serializers.URLField(required=False, allow_blank=True, allow_null=True, help_text="URL video khóa học (ví dụ: YouTube hoặc link video trực tiếp)")
    video_file = serializers.FileField(required=False, allow_null=True, help_text="File video khóa học (nếu không dùng URL)")
    thumbnail = serializers.ImageField(required=False, allow_null=True, help_text="Ảnh bìa khóa học")

    class Meta:
        model = models.Course
        fields = ["id", "subject", "subject_slug", "subject_title", "title", "description", "introduction", "grade", "owner", "slug", "published", "published_at", "created_on", "updated_on", "createdAt", "updatedAt", "status", "enrollments", "lessonsCount", "video_url", "video_file", "thumbnail"]
        read_only_fields = ["id", "published_at", "created_on", "updated_on", "createdAt", "updatedAt", "status", "enrollments", "lessonsCount"]

    def get_status(self, obj):
        """Compute status from published boolean"""
        if obj.published:
            return "published"
        # For now, we only have draft and published. Archived can be added later if needed.
        return "draft"

    def get_createdAt(self, obj):
        return obj.created_on.isoformat() if obj.created_on else None

    def get_updatedAt(self, obj):
        return obj.updated_on.isoformat() if obj.updated_on else None
    
    def get_enrollments(self, obj):
        """Get enrollment count"""
        if hasattr(obj, 'enrollments_count'):
            return obj.enrollments_count
        return obj.enrollments.count() if hasattr(obj, 'enrollments') else 0
    
    def get_lessonsCount(self, obj):
        """Get total published lessons count"""
        from content.models import Lesson
        return Lesson.objects.filter(module__course=obj, published=True).count()

    def validate(self, attrs):
        if 'price' in getattr(self, 'initial_data', {}):
            raise serializers.ValidationError({
                'price': 'SmartKid không bán khóa học; học sinh ghi danh miễn phí.'
            })

        # If subject_slug is provided, try to find Subject by slug
        subject_slug = attrs.get("subject_slug")
        if subject_slug and not attrs.get("subject"):
            # Map frontend subject names to backend slugs and titles
            subject_mapping = {
                "math": {"slug": "toan", "title": "Toán"},
                "vietnamese": {"slug": "tieng-viet", "title": "Tiếng Việt"},
                "english": {"slug": "tieng-anh", "title": "Tiếng Anh"},
                "science": {"slug": "khoa-hoc", "title": "Khoa học"},
                "history": {"slug": "lich-su", "title": "Lịch sử"}
            }
            mapping = subject_mapping.get(subject_slug, {"slug": subject_slug, "title": subject_slug.title()})
            slug = mapping["slug"]
            title = mapping["title"]
            
            # Try to find by slug first
            subject = models.Subject.objects.filter(slug=slug).first()
            if not subject:
                # Try to find by title
                subject = models.Subject.objects.filter(title__icontains=title).first()
            if not subject:
                # Create if not found
                subject = models.Subject.objects.create(slug=slug, title=title)
            attrs["subject"] = subject
        
        # Remove empty file fields to avoid validation errors
        # If thumbnail is empty string or None, remove it
        if 'thumbnail' in attrs and (attrs['thumbnail'] is None or attrs['thumbnail'] == ''):
            attrs.pop('thumbnail', None)
        if 'video_file' in attrs and (attrs['video_file'] is None or attrs['video_file'] == ''):
            attrs.pop('video_file', None)
            
        return attrs

    def to_domain(self) -> CourseDomain:
        """
        Convert validated_data -> CourseDomain (for create/update commands).
        We pass subject_id and owner_id as strings/ints for the domain.
        """
        d = self.validated_data
        subject = d.get("subject")
        owner = d.get("owner")
        course = CourseDomain(
            title=d["title"],
            subject_id=_maybe_pk_to_id(subject),
            description=d.get("description"),
            grade=d.get("grade"),
            owner_id=(owner.id if owner else None),
            slug=d.get("slug"),
            introduction=d.get("introduction"),
            video_url=d.get("video_url")
        )
        course.validate()
        return course

    @staticmethod
    def from_domain(domain: CourseDomain) -> Dict[str, Any]:
        result = domain.to_dict()
        # Add status field computed from published
        result['status'] = 'published' if domain.published else 'draft'
        created_on = result.get('created_on')
        if created_on:
            result['createdAt'] = created_on.isoformat() if hasattr(created_on, 'isoformat') else created_on
        updated_on = result.get('updated_on')
        if updated_on:
            result['updatedAt'] = updated_on.isoformat() if hasattr(updated_on, 'isoformat') else updated_on
        # Add thumbnail and video_file URLs if available
        from django.conf import settings
        # Handle thumbnail - ensure it's a string, not a file object
        thumbnail = getattr(domain, 'thumbnail', None)
        if thumbnail:
            # If it's a file object, get the name. If it's already a string, use it directly
            if hasattr(thumbnail, 'name'):
                thumb_str = thumbnail.name
            else:
                thumb_str = str(thumbnail)
            if thumb_str and thumb_str != 'None':
                result['thumbnail'] = f"{settings.MEDIA_URL}{thumb_str}" if not thumb_str.startswith('http') else thumb_str
        # Handle video_file - ensure it's a string, not a file object
        video_file = getattr(domain, 'video_file', None)
        if video_file:
            # If it's a file object, get the name. If it's already a string, use it directly
            if hasattr(video_file, 'name'):
                video_str = video_file.name
            else:
                video_str = str(video_file)
            if video_str and video_str != 'None':
                result['video_file'] = f"{settings.MEDIA_URL}{video_str}" if not video_str.startswith('http') else video_str
        return result


class ModuleSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    course = serializers.PrimaryKeyRelatedField(queryset=models.Course.objects.all(), required=False, allow_null=True)
    title = serializers.CharField(max_length=255)
    position = serializers.IntegerField(default=0, min_value=0)

    class Meta:
        model = models.Module
        fields = ["id", "course", "title", "position"]
        read_only_fields = ["id"]

    def to_domain(self, course_id=None) -> ModuleDomain:
        d = self.validated_data
        # Use course_id from parameter if provided, otherwise from data
        course_id_value = course_id or _maybe_pk_to_id(d.get("course"))
        if not course_id_value:
            raise serializers.ValidationError("course_id is required")
        domain = ModuleDomain(
            course_id=str(course_id_value),
            title=d["title"],
            position=d.get("position", 0)
        )
        domain.validate()
        return domain

    @staticmethod
    def from_domain(domain: ModuleDomain) -> Dict[str, Any]:
        return domain.to_dict()


class ContentBlockSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    lesson_version = serializers.PrimaryKeyRelatedField(queryset=models.LessonVersion.objects.all(), source="lesson_version_id")
    type = serializers.ChoiceField(choices=[("text", "Text"), ("image", "Image"), ("video", "Video"), ("quiz", "Quiz"), ("exploration_ref", "ExplorationRef")])
    position = serializers.IntegerField(default=0, min_value=0)
    payload = serializers.JSONField()

    class Meta:
        model = models.ContentBlock
        fields = ["id", "lesson_version", "type", "position", "payload"]
        read_only_fields = ["id"]

    def to_domain(self) -> ContentBlockDomain:
        d = self.validated_data
        lesson_version = d.get("lesson_version")  # this will be a LessonVersion model instance or PK depending on DRF
        # map to lesson_version_id
        lesson_version_id = _maybe_pk_to_id(lesson_version)
        cb = ContentBlockDomain(
            lesson_version_id=lesson_version_id,
            type=d["type"],
            position=d.get("position", 0),
            payload=d.get("payload", {})
        )
        cb.validate_payload()
        return cb

    @staticmethod
    def from_domain(domain: ContentBlockDomain) -> Dict[str, Any]:
        return domain.to_dict()


class LessonVersionSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    lesson = serializers.PrimaryKeyRelatedField(queryset=models.Lesson.objects.all(), source="lesson_id")
    version = serializers.IntegerField(read_only=True)
    status = serializers.ChoiceField(choices=[("draft", "Draft"), ("review", "Review"), ("published", "Published")], default="draft")
    author = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), allow_null=True, required=False)
    content = serializers.JSONField()
    change_summary = serializers.CharField(allow_blank=True, required=False)
    created_at = serializers.DateTimeField(read_only=True)
    published_at = serializers.DateTimeField(read_only=True)
    # nested read-only list of content blocks (if prefetched)
    content_blocks = ContentBlockSerializer(many=True, read_only=True)

    class Meta:
        model = models.LessonVersion
        fields = ["id", "lesson", "version", "status", "author", "content", "change_summary", "created_at", "published_at", "content_blocks"]
        read_only_fields = ["id", "version", "created_at", "published_at", "content_blocks"]

    def to_domain(self) -> LessonVersionDomain:
        """
        For creation/updating of lesson versions.
        If instance exists, it's an update; for create, version will be assigned by domain/Service.
        """

        d = self.validated_data
        lesson = d.get("lesson")
        lesson_id = _maybe_pk_to_id(lesson)
        author = d.get("author")
        lv = LessonVersionDomain(
            lesson_id=lesson_id,
            version=d.get("version", 0) or 0,  # service will set real version on create
            status=d.get("status", "draft"),
            author_id=(author.id if author else None),
            content=d.get("content", {}),
            change_summary=d.get("change_summary")
        )
        # Validate content structure (this will validate content blocks payload)
        lv.validate_content()
        return lv

    @staticmethod
    def from_domain(domain: LessonVersionDomain) -> Dict[str, Any]:
        return domain.to_dict()


class LessonSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    module = serializers.PrimaryKeyRelatedField(queryset=models.Module.objects.all(), source="module_id")
    title = serializers.CharField(max_length=255)
    position = serializers.IntegerField(default=0, min_value=0)
    content_type = serializers.ChoiceField(
        choices=[
            ("lesson", "Lesson"),
            ("exploration", "Exploration"),
            ("exercise", "Exercise"),
            ("quiz", "Quiz"),
            ("video", "Video"),
            ("pdf", "PDF"),
            ("text", "Text"),
            ("document", "Document"),
        ],
        default="lesson"
    )
    published = serializers.BooleanField(default=False)
    introduction = serializers.CharField(allow_blank=True, required=False, help_text="Giới thiệu bài học")
    video_url = serializers.URLField(allow_blank=True, required=False, allow_null=True, help_text="URL video bài học")
    video_file = serializers.FileField(required=False, allow_null=True, help_text="File video bài học")
    document_file = serializers.FileField(required=False, allow_null=True, help_text="File tài liệu (PDF, DOCX)")
    text_content = serializers.CharField(allow_blank=True, required=False, allow_null=True, help_text="Nội dung văn bản")
    requires_exercise_completion = serializers.BooleanField(default=False, help_text="Yêu cầu hoàn thành bài tập trước khi tiếp tục")
    video_transcript = serializers.CharField(allow_blank=True, required=False, allow_null=True, help_text="Nội dung lời thoại video")
    versions = LessonVersionSerializer(many=True, read_only=True)

    class Meta:
        model = models.Lesson
        fields = ["id", "module", "title", "position", "content_type", "published", "introduction", "video_url", "video_file", "document_file", "text_content", "requires_exercise_completion", "video_transcript", "versions"]
        read_only_fields = ["id", "versions"]

    def to_domain(self) -> LessonDomain:
        d = self.validated_data
        module = d.get("module")
        lesson = LessonDomain(
            module_id=_maybe_pk_to_id(module),
            title=d["title"],
            position=d.get("position", 0),
            content_type=d.get("content_type", "lesson"),
            published=d.get("published", False)
        )
        lesson.validate()
        return lesson

    @staticmethod
    def from_domain(domain: LessonDomain) -> Dict[str, Any]:
        return domain.to_dict()


class ExplorationStateSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    exploration = serializers.PrimaryKeyRelatedField(queryset=models.Exploration.objects.all(), source="exploration_id")
    name = serializers.CharField(max_length=255)
    content = serializers.JSONField()
    interaction = serializers.JSONField()

    class Meta:
        model = models.ExplorationState
        fields = ["id", "exploration", "name", "content", "interaction"]
        read_only_fields = ["id"]

    def to_domain(self) -> ExplorationStateDomain:
        d = self.validated_data
        exploration = d.get("exploration")
        state = ExplorationStateDomain(
            exploration_id=_maybe_pk_to_id(exploration),
            name=d["name"],
            content=d.get("content", {}),
            interaction=d.get("interaction", {})
        )
        state.validate()
        return state

    @staticmethod
    def from_domain(domain: ExplorationStateDomain) -> Dict[str, Any]:
        return domain.to_dict()


class ExplorationTransitionSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    exploration = serializers.PrimaryKeyRelatedField(queryset=models.Exploration.objects.all(), source="exploration_id")
    from_state = serializers.PrimaryKeyRelatedField(queryset=models.ExplorationState.objects.all())
    to_state = serializers.PrimaryKeyRelatedField(queryset=models.ExplorationState.objects.all())
    condition = serializers.JSONField()

    class Meta:
        model = models.ExplorationTransition
        fields = ["id", "exploration", "from_state", "to_state", "condition"]
        read_only_fields = ["id"]

    def to_domain(self) -> ExplorationTransitionDomain:
        d = self.validated_data
        exploration = d.get("exploration")
        from_state = d.get("from_state")
        to_state = d.get("to_state")
        t = ExplorationTransitionDomain(
            exploration_id=_maybe_pk_to_id(exploration),
            from_state=(_maybe_pk_to_id(from_state) if from_state else d.get("from_state")),
            to_state=(_maybe_pk_to_id(to_state) if to_state else d.get("to_state")),
            condition=d.get("condition", {})
        )
        t.validate()
        return t

    @staticmethod
    def from_domain(domain: ExplorationTransitionDomain) -> Dict[str, Any]:
        return domain.to_dict()


class ExplorationSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    title = serializers.CharField(max_length=255)
    owner = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), allow_null=True, required=False)
    language = serializers.CharField(max_length=8, default="vi")
    initial_state_name = serializers.CharField(max_length=255, allow_null=True, required=False)
    schema_version = serializers.IntegerField(default=1)
    published = serializers.BooleanField(default=False)
    states = ExplorationStateSerializer(many=True, read_only=True)
    transitions = ExplorationTransitionSerializer(many=True, read_only=True)

    class Meta:
        model = models.Exploration
        fields = ["id", "title", "owner", "language", "initial_state_name", "schema_version", "published", "states", "transitions"]
        read_only_fields = ["id", "states", "transitions"]

    def to_domain(self) -> ExplorationDomain:
        d = self.validated_data
        owner = d.get("owner")
        exp = ExplorationDomain(
            title=d["title"],
            owner_id=(owner.id if owner else None),
            language=d.get("language", "vi"),
            initial_state_name=d.get("initial_state_name"),
            schema_version=d.get("schema_version", 1),
            published=d.get("published", False)
        )
        exp.validate()
        return exp

    @staticmethod
    def from_domain(domain: ExplorationDomain) -> Dict[str, Any]:
        return domain.to_dict()


class ContentLibrarySerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    title = serializers.CharField(max_length=255)
    subject = serializers.ChoiceField(choices=[
        ('math', 'Toán'),
        ('vietnamese', 'Tiếng Việt'),
        ('english', 'Tiếng Anh'),
        ('science', 'Khoa học'),
        ('history', 'Lịch sử')
    ])
    type = serializers.ChoiceField(choices=[
        ('video', 'Video'),
        ('pdf', 'PDF'),
        ('doc', 'Tài liệu'),
        ('quiz', 'Quiz'),
        ('text', 'Văn bản'),
        ('image', 'Hình ảnh')
    ])
    grade_band = serializers.ChoiceField(choices=[
        ('Khối 1', 'Khối 1'),
        ('Khối 2', 'Khối 2'),
        ('Khối 3', 'Khối 3'),
        ('Khối 4', 'Khối 4'),
        ('Khối 5', 'Khối 5')
    ])
    owner = serializers.PrimaryKeyRelatedField(read_only=True, allow_null=True)
    meta = serializers.JSONField(default=dict, required=False)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    updatedAt = serializers.SerializerMethodField()

    class Meta:
        model = models.ContentLibrary
        fields = ["id", "title", "subject", "type", "grade_band", "owner", "meta", "created_at", "updated_at", "updatedAt"]
        read_only_fields = ["id", "owner", "created_at", "updated_at", "updatedAt"]

    def get_updatedAt(self, obj):
        """Format updated_at for frontend"""
        return obj.updated_at.strftime('%d/%m/%Y') if obj.updated_at else ''


# -----------------------
# Command / Input-only Serializers (to produce Domain Command objects)
# -----------------------
# These are used by endpoints for create/publish actions and convert to domain commands

# Stub implementations - to be fully implemented later
CreateCourseInputSerializer = CourseSerializer
AddModuleInputSerializer = ModuleSerializer
CreateLessonInputSerializer = LessonSerializer
CreateLessonVersionInputSerializer = LessonVersionSerializer
PublishLessonVersionInputSerializer = LessonVersionSerializer
AddContentBlockInputSerializer = ContentBlockSerializer
CreateExplorationInputSerializer = ExplorationSerializer
AddExplorationStateInputSerializer = ExplorationStateSerializer
AddExplorationTransitionInputSerializer = ExplorationTransitionSerializer

# Read-only serializers with nested data
CourseDetailReadSerializer = CourseSerializer
ModuleReadSerializer = ModuleSerializer
LessonReadSerializer = LessonSerializer
LessonVersionReadSerializer = LessonVersionSerializer
