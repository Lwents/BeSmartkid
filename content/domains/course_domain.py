import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, Iterable, Tuple
from collections import deque

from content.services.exceptions import DomainValidationError, NotFoundError, InvalidOperation
from content.domains.module_domain import ModuleDomain


class CourseDomain:
    """
    Aggregate root: Course gồm nhiều Module; Module có Lesson; Lesson có LessonVersion.
    Business rules (encoded here):
    - Course.slug format validated here (but uniqueness must be checked by app layer).
    - Publish rules (default policy): course can be published only when:
        * it has >=1 module
        * and there exists at least one published lesson version in the course
      (You can call `publish()` with stricter flag `require_all_lessons_published=True`).
    - Course.owner can be None (system content).
    """

    def __init__(self,
                 title: str,
                 subject_id: Optional[str] = None,
                 description: Optional[str] = None,
                 grade: Optional[str] = None,
                 owner_id: Optional[int] = None,
                 slug: Optional[str] = None,
                 id: Optional[str] = None,
                 published: bool = False,
                 published_at: Optional[datetime] = None,
                 created_on: Optional[datetime] = None,
                 updated_on: Optional[datetime] = None,
                 introduction: Optional[str] = None,
                 video_url: Optional[str] = None):
        self.id = id or str(uuid.uuid4())
        self.title = title
        self.subject_id = subject_id
        self.description = description
        self.introduction = introduction
        self.grade = grade
        self.owner_id = owner_id
        self.slug = slug
        self.published = published
        self.published_at = published_at
        self.created_on = created_on
        self.updated_on = updated_on
        self.video_url = video_url
        # contained aggregates (in-memory)
        self.modules: List["ModuleDomain"] = []
        self.validate()

    def validate(self):
        if not self.title or not self.title.strip():
            raise DomainValidationError("Course.title is required.")
        if self.slug and (" " in self.slug or len(self.slug) < 2):
            raise DomainValidationError("Course.slug must be at least 2 chars and have no spaces.")
        # grade length check
        if self.grade and len(str(self.grade)) > 16:
            raise DomainValidationError("Course.grade too long.")

    # ---- Module manipulation (aggregate boundary) ----
    def add_module(self, title: str, position: Optional[int] = None) -> "ModuleDomain":
        if not title or not title.strip():
            raise DomainValidationError("Module title required.")
        position = position if position is not None else len(self.modules)
        if position < 0 or position > len(self.modules):
            raise DomainValidationError("position out of range.")
        # shift positions of existing modules if needed
        for m in self.modules:
            if m.position >= position:
                m.position += 1
        module = ModuleDomain(course_id=self.id, title=title, position=position)
        self.modules.append(module)
        # normalize to keep consistent ordering
        self._normalize_modules_positions()
        return module

    def remove_module(self, module_id: str):
        found = None
        for m in self.modules:
            if m.id == module_id:
                found = m
                break
        if not found:
            raise NotFoundError("Module not found in course.")
        self.modules.remove(found)
        self._normalize_modules_positions()

    def move_module(self, module_id: str, new_position: int):
        if new_position < 0 or new_position >= len(self.modules):
            raise DomainValidationError("new_position out of range.")
        module = next((m for m in self.modules if m.id == module_id), None)
        if not module:
            raise NotFoundError("Module not found.")
        self.modules.remove(module)
        self.modules.insert(new_position, module)
        self._normalize_modules_positions()

    def _normalize_modules_positions(self):
        # keep positions sequential 0..n-1
        self.modules.sort(key=lambda m: m.position)
        for idx, m in enumerate(self.modules):
            m.position = idx

    def get_module(self, module_id: str) -> "ModuleDomain":
        m = next((m for m in self.modules if m.id == module_id), None)
        if not m:
            raise NotFoundError("Module not found.")
        return m

    def list_module_summaries(self) -> List[Dict[str, Any]]:
        return [m.to_dict(summary=True) for m in self.modules]

    # ---- Publishing rules ----
    def can_publish(self, require_all_lessons_published: bool = False) -> Tuple[bool, str]:
        # Rule 1: phải có ít nhất 1 chương
        if not self.modules:
            return False, "Khóa học cần ít nhất 1 chương."

        # Rule 2: phải có ít nhất 1 bài học
        has_any_lesson = any(m.lessons for m in self.modules)
        if not has_any_lesson:
            return False, "Khóa học cần ít nhất 1 bài học."

        # Rule 3: cần ít nhất 1 bài học đã xuất bản version
        any_published = False
        for m in self.modules:
            for l in m.lessons:
                if l.has_published_version():
                    any_published = True
                    break
            if any_published:
                break
        if not any_published:
            return False, "Cần ít nhất 1 bài học đã xuất bản (chọn bài học và xuất bản phiên bản)."

        # Strict mode: toàn bộ bài học đều phải có version đã xuất bản
        if require_all_lessons_published:
            for m in self.modules:
                for l in m.lessons:
                    if not l.has_published_version():
                        return False, f"Bài học “{l.title}” chưa có phiên bản đã xuất bản."

        return True, "OK"

    def publish(self, require_all_lessons_published: bool = False):
        ok, reason = self.can_publish(require_all_lessons_published=require_all_lessons_published)
        if not ok:
            raise InvalidOperation(f"Cannot publish course: {reason}")
        self.published = True
        self.published_at = str(uuid.uuid4())

    def unpublish(self):
        # no complex rule: unpublish allowed anytime
        self.published = False
        self.published_at = None

    # ---- Serialization helpers ----
    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "subject_id": self.subject_id,
            "description": self.description,
            "introduction": self.introduction,
            "grade": self.grade,
            "owner_id": self.owner_id,
            "slug": self.slug,
            "published": self.published,
            "published_at": self.published_at,
            "created_on": self.created_on,
            "updated_on": self.updated_on,
            "video_url": self.video_url,
            "video_file": getattr(self, 'video_file', None),
            "thumbnail": getattr(self, 'thumbnail', None),
            "modules": [m.to_dict() for m in self.modules]
        }

    @classmethod
    def from_model(cls, model):
        """
        Optional helper: nếu có Django model, mapping sang domain.
        model expected to have attributes and related loaders for modules->lessons->versions.
        """
        c = cls(
            title=model.title, 
            subject_id=(str(model.subject.id) if getattr(model,'subject',None) else None),
            description=model.description, 
            introduction=getattr(model, 'introduction', None),
            grade=model.grade, 
            owner_id=(getattr(model,'owner',None).id if getattr(model,'owner',None) else None),
            slug=getattr(model,'slug',None), 
            id=str(model.id), 
            published=model.published, 
            published_at=getattr(model,'published_at',None),
            created_on=getattr(model, 'created_on', None),
            updated_on=getattr(model, 'updated_on', None),
            video_url=getattr(model, 'video_url', None)
        )
        # Set thumbnail and video_file separately as they're not in __init__
        # Convert file fields to string paths, handling both file objects and string paths
        if hasattr(model, 'thumbnail') and model.thumbnail:
            # If it's a file object, get the name. If it's already a string, use it directly
            if hasattr(model.thumbnail, 'name'):
                c.thumbnail = model.thumbnail.name
            else:
                c.thumbnail = str(model.thumbnail) if model.thumbnail else None
        if hasattr(model, 'video_file') and model.video_file:
            # If it's a file object, get the name. If it's already a string, use it directly
            if hasattr(model.video_file, 'name'):
                c.video_file = model.video_file.name
            else:
                c.video_file = str(model.video_file) if model.video_file else None
        # If model has prefetched modules/lessons/versions we can build nested domain objects
        if hasattr(model, "modules_prefetched") and model.modules_prefetched:
            for mod_m in model.modules_prefetched:
                mod_d = ModuleDomain.from_model(mod_m)
                c.modules.append(mod_d)
        return c


# Command classes for course operations
class CreateCourseDomain:
    """Command object for creating a course."""
    def __init__(self, title: str, subject_id: Optional[str] = None, description: Optional[str] = None,
                 grade: Optional[str] = None, owner_id: Optional[int] = None, slug: Optional[str] = None,
                 introduction: Optional[str] = None, video_url: Optional[str] = None):
        self.title = title
        self.subject_id = subject_id
        self.description = description
        self.introduction = introduction
        self.grade = grade
        self.owner_id = owner_id
        self.slug = slug
        self.video_url = video_url

    def validate(self):
        if not self.title or not self.title.strip():
            raise DomainValidationError("Course title required.")


class UpdateCourseDomain:
    """Command object for updating a course."""
    def __init__(self, title: Optional[str] = None, subject_id: Optional[str] = None,
                 description: Optional[str] = None, grade: Optional[str] = None, slug: Optional[str] = None,
                 introduction: Optional[str] = None, published: Optional[bool] = None):
        self.title = title
        self.subject_id = subject_id
        self.description = description
        self.grade = grade
        self.slug = slug
        self.introduction = introduction
        self.published = published

    def validate(self):
        if self.title is not None and (not self.title or not self.title.strip()):
            raise DomainValidationError("Course title cannot be empty.")


class CoursePublishDomain:
    """Command object for publishing a course."""
    def __init__(self, course_id: str, require_all_lessons_published: bool = False):
        self.course_id = course_id
        self.require_all_lessons_published = require_all_lessons_published

    def validate(self):
        if not self.course_id:
            raise DomainValidationError("Course ID required.")


class CourseAssignOwnerDomain:
    """Command object for assigning owner to a course."""
    def __init__(self, course_id: str, owner_id: int):
        self.course_id = course_id
        self.owner_id = owner_id

    def validate(self):
        if not self.course_id:
            raise DomainValidationError("Course ID required.")
        if not self.owner_id:
            raise DomainValidationError("Owner ID required.")
