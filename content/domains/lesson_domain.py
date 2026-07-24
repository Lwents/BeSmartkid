import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, Iterable, Tuple
from collections import deque

from content.services.exceptions import DomainValidationError, NotFoundError, InvalidOperation
from content.domains.lesson_version_domain import LessonVersionDomain
from content.domains.value_objects import CreateLessonVersionCommand



class LessonDomain:
    VALID_CONTENT_TYPES = ("lesson", "exploration", "exercise", "quiz", "video", "pdf", "text", "document")

    def __init__(self,
                 module_id: str,
                 title: str,
                 position: int = 0,
                 content_type: str = "lesson",
                 published: bool = False,
                 id: Optional[str] = None):
        self.id = id or str(uuid.uuid4())
        self.module_id = module_id
        self.title = title
        self.position = int(position)
        self.content_type = content_type
        self.published = published  # convenience flag; canonical source is versions
        self.versions: List["LessonVersionDomain"] = []
        self.validate()

    def validate(self):
        if not self.module_id:
            raise DomainValidationError("Lesson.module_id required.")
        if not self.title or not self.title.strip():
            raise DomainValidationError("Lesson.title required.")
        if self.content_type not in self.VALID_CONTENT_TYPES:
            raise DomainValidationError("Invalid Lesson.content_type.")

    def create_version(self, author_id: Optional[int], content: Dict[str, Any], change_summary: Optional[str] = None) -> "LessonVersionDomain":
        # Next version number = max existing +1 or 1
        next_v = 1 + (max((v.version for v in self.versions), default=0))
        lv = LessonVersionDomain(lesson_id=self.id, version=next_v, status="draft", author_id=author_id, content=content, change_summary=change_summary)
        # validate content blocks if present
        lv.validate_content()
        self.versions.append(lv)
        return lv

    def get_version(self, version: int) -> "LessonVersionDomain":
        v = next((x for x in self.versions if x.version == version), None)
        if not v:
            raise NotFoundError("LessonVersion not found.")
        return v

    def get_latest_version(self) -> Optional["LessonVersionDomain"]:
        if not self.versions:
            return None
        return max(self.versions, key=lambda x: x.version)

    def has_published_version(self) -> bool:
        return any(v.status == "published" for v in self.versions)

    def publish_version(self, version: int):
        target = self.get_version(version)
        # Business rule: cannot publish empty version
        if not target.content or (isinstance(target.content, dict) and not target.content.get("content_blocks") and not target.content.get("structure")):
            raise InvalidOperation("Cannot publish an empty lesson version.")
        # Unpublish any other published versions (domain enforces invariant)
        for v in self.versions:
            if v.status == "published" and v.version != version:
                v.status = "review"
                v.published_at = None
        target.status = "published"
        target.published_at = datetime.now()
        # update lesson flag
        self.published = True
        return target

    def unpublish_all_versions(self):
        for v in self.versions:
            if v.status == "published":
                v.status = "review"
                v.published_at = None
        self.published = False

    def to_dict(self):
        result = {
            "id": self.id,
            "module_id": self.module_id,
            "title": self.title,
            "position": self.position,
            "content_type": self.content_type,
            "published": self.published,
            "versions": [v.to_dict() for v in self.versions]
        }
        # Add new fields if available
        if hasattr(self, 'introduction'):
            result['introduction'] = self.introduction
        if hasattr(self, 'video_url'):
            result['video_url'] = self.video_url
        if hasattr(self, 'video_file'):
            result['video_file'] = self.video_file
        if hasattr(self, 'document_file'):
            result['document_file'] = self.document_file
        if hasattr(self, 'text_content'):
            result['text_content'] = self.text_content
        if hasattr(self, 'requires_exercise_completion'):
            result['requires_exercise_completion'] = self.requires_exercise_completion
        if hasattr(self, 'video_transcript'):
            result['video_transcript'] = self.video_transcript
        return result

    @classmethod
    def from_model(cls, model):
        l = cls(module_id=str(getattr(model,'module_id',None) or ""), title=model.title, position=model.position, content_type=model.content_type, published=model.published, id=str(model.id))
        # Add new fields
        if hasattr(model, 'introduction'):
            l.introduction = model.introduction
        if hasattr(model, 'video_url'):
            l.video_url = model.video_url
        if hasattr(model, 'video_file') and model.video_file:
            l.video_file = str(model.video_file)
        if hasattr(model, 'document_file') and model.document_file:
            l.document_file = str(model.document_file)
        if hasattr(model, 'text_content'):
            l.text_content = model.text_content
        if hasattr(model, 'requires_exercise_completion'):
            l.requires_exercise_completion = model.requires_exercise_completion
        if hasattr(model, 'video_transcript'):
            l.video_transcript = model.video_transcript
        # Load versions - kiểm tra cả prefetched và related
        if hasattr(model, "versions_prefetched") and model.versions_prefetched:
            for v_m in model.versions_prefetched:
                l.versions.append(LessonVersionDomain.from_model(v_m))
        elif hasattr(model, 'versions'):
            # Nếu không có prefetch, load trực tiếp từ related manager
            try:
                from content.domains.lesson_version_domain import LessonVersionDomain
                for v_m in model.versions.all():
                    l.versions.append(LessonVersionDomain.from_model(v_m))
            except Exception:
                pass  # Nếu không load được, bỏ qua
        return l


# Command classes for lesson operations
class CreateLessonDomain:
    """Command object for creating a lesson."""
    def __init__(self, module_id: str, title: str, position: int = 0, content_type: str = "lesson"):
        self.module_id = module_id
        self.title = title
        self.position = position
        self.content_type = content_type

    def validate(self):
        if not self.module_id:
            raise DomainValidationError("Lesson module_id required.")
        if not self.title or not self.title.strip():
            raise DomainValidationError("Lesson title required.")
        if self.content_type not in LessonDomain.VALID_CONTENT_TYPES:
            raise DomainValidationError("Invalid lesson content_type.")


class UpdateLessonDomain:
    """Command object for updating a lesson."""
    def __init__(self, title: Optional[str] = None, position: Optional[int] = None, content_type: Optional[str] = None):
        self.title = title
        self.position = position
        self.content_type = content_type

    def validate(self):
        if self.title is not None and (not self.title or not self.title.strip()):
            raise DomainValidationError("Lesson title cannot be empty.")
        if self.content_type is not None and self.content_type not in LessonDomain.VALID_CONTENT_TYPES:
            raise DomainValidationError("Invalid lesson content_type.")


class PublishLessonDomain:
    """Command object for publishing a lesson."""
    def __init__(self, lesson_id: str, version: int):
        self.lesson_id = lesson_id
        self.version = version

    def validate(self):
        if not self.lesson_id:
            raise DomainValidationError("Lesson ID required.")
        if self.version < 1:
            raise DomainValidationError("Version must be >= 1.")


class ReorderLessonsDomain:
    """Command object for reordering lessons."""
    def __init__(self, module_id: str, lesson_positions: List[Tuple[str, int]]):
        self.module_id = module_id
        self.lesson_positions = lesson_positions

    def validate(self):
        if not self.module_id:
            raise DomainValidationError("Module ID required.")
        if not self.lesson_positions:
            raise DomainValidationError("Lesson positions required.")
