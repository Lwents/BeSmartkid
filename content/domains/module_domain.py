import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, Iterable, Tuple
from collections import deque

from content.services.exceptions import DomainValidationError, NotFoundError, InvalidOperation
from content.domains.lesson_domain import LessonDomain



class ModuleDomain:
    def __init__(self, course_id: str, title: str, position: int = 0, id: Optional[str] = None):
        self.id = id or str(uuid.uuid4())
        self.course_id = course_id
        self.title = title
        self.position = int(position)
        self.lessons: List["LessonDomain"] = []
        self.validate()

    def validate(self):
        if not self.course_id:
            raise DomainValidationError("Module.course_id required.")
        if not self.title or not self.title.strip():
            raise DomainValidationError("Module.title required.")
        if self.position < 0:
            raise DomainValidationError("Module.position must be >= 0")

    def add_lesson(self, title: str, content_type: str = "lesson", position: Optional[int] = None) -> "LessonDomain":
        if not title or not title.strip():
            raise DomainValidationError("Lesson title required.")
        position = position if position is not None else len(self.lessons)
        if position < 0 or position > len(self.lessons):
            raise DomainValidationError("position out of range.")
        for l in self.lessons:
            if l.position >= position:
                l.position += 1
        lesson = LessonDomain(module_id=self.course_id + ":" + self.id, title=title, position=position, content_type=content_type)
        # Note: lesson.module_id intentionally encodes course+module key for uniqueness in-memory;
        # in persistence layer you'll map properly to Module FK.
        self.lessons.append(lesson)
        self._normalize_lessons_positions()
        return lesson

    def remove_lesson(self, lesson_id: str):
        l = next((x for x in self.lessons if x.id == lesson_id), None)
        if not l:
            raise NotFoundError("Lesson not found in module.")
        self.lessons.remove(l)
        self._normalize_lessons_positions()

    def _normalize_lessons_positions(self):
        self.lessons.sort(key=lambda x: x.position)
        for idx, l in enumerate(self.lessons):
            l.position = idx

    def get_lesson(self, lesson_id: str) -> "LessonDomain":
        l = next((x for x in self.lessons if x.id == lesson_id), None)
        if not l:
            raise NotFoundError("Lesson not found.")
        return l

    def to_dict(self, summary: bool = False):
        base = {"id": self.id, "course_id": self.course_id, "title": self.title, "position": self.position}
        if summary:
            base["lessons_count"] = len(self.lessons)
        else:
            base["lessons"] = [l.to_dict() for l in self.lessons]
        return base

    @classmethod
    def from_model(cls, model):
        # model expected to have .id, .title, .position and maybe prefetched lessons
        m = cls(course_id=(str(getattr(model,'course_id', None)) or ""), title=model.title, position=model.position, id=str(model.id))
        if hasattr(model, "lessons_prefetched") and model.lessons_prefetched:
            for l_m in model.lessons_prefetched:
                m.lessons.append(LessonDomain.from_model(l_m))
        return m


# Command classes for module operations
class CreateModuleDomain:
    """Command object for creating a module."""
    def __init__(self, course_id: str, title: str, position: int = 0):
        self.course_id = course_id
        self.title = title
        self.position = position

    def validate(self):
        if not self.course_id:
            raise DomainValidationError("Module course_id required.")
        if not self.title or not self.title.strip():
            raise DomainValidationError("Module title required.")


class UpdateModuleDomain:
    """Command object for updating a module."""
    def __init__(self, title: Optional[str] = None, position: Optional[int] = None):
        self.title = title
        self.position = position

    def validate(self):
        if self.title is not None and (not self.title or not self.title.strip()):
            raise DomainValidationError("Module title cannot be empty.")


class ReorderModulesDomain:
    """Command object for reordering modules."""
    def __init__(self, course_id: str, module_positions: List[Tuple[str, int]]):
        self.course_id = course_id
        self.module_positions = module_positions

    def validate(self):
        if not self.course_id:
            raise DomainValidationError("Course ID required.")
        if not self.module_positions:
            raise DomainValidationError("Module positions required.")