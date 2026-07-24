import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, Iterable, Tuple
from collections import deque

from content.services.exceptions import DomainValidationError

@dataclass
class CreateCourseCommand:
    title: str
    subject_id: Optional[str] = None
    description: Optional[str] = None
    grade: Optional[str] = None
    owner_id: Optional[int] = None
    slug: Optional[str] = None

    def validate(self):
        if not self.title or not self.title.strip():
            raise DomainValidationError("Course title is required.")
        if self.slug and (" " in self.slug or len(self.slug) < 2):
            raise DomainValidationError("Slug must be at least 2 chars and contain no spaces.")
        # grade format allowed: '1'..'12', 'K', 'pre', or custom strings
        if self.grade and len(str(self.grade)) > 16:
            raise DomainValidationError("Invalid grade length.")

@dataclass
class AddModuleCommand:
    course_id: str
    title: str
    position: Optional[int] = None

    def validate(self):
        if not self.course_id:
            raise DomainValidationError("course_id required.")
        if not self.title or not self.title.strip():
            raise DomainValidationError("module title required.")

@dataclass
class CreateLessonCommand:
    module_id: str
    title: str
    content_type: str = "lesson"  # lesson|exploration|exercise|quiz|video|pdf|text|document
    position: Optional[int] = None

    def validate(self):
        if not self.module_id:
            raise DomainValidationError("module_id required.")
        if not self.title or not self.title.strip():
            raise DomainValidationError("lesson title required.")
        if self.content_type not in ("lesson", "exploration", "exercise", "quiz", "video", "pdf", "text", "document"):
            raise DomainValidationError("Invalid content_type.")

@dataclass
class CreateLessonVersionCommand:
    lesson_id: str
    author_id: Optional[int]
    content: Dict[str, Any]  # overall JSON structure or canonical representation
    change_summary: Optional[str] = None

    def validate(self):
        if not self.lesson_id:
            raise DomainValidationError("lesson_id required.")
        if not isinstance(self.content, dict):
            raise DomainValidationError("content must be an object/dict.")
        # Basic rule: content should contain at least one content block or structured payload.
        if not self.content:
            raise DomainValidationError("content must not be empty.")

@dataclass
class PublishLessonVersionCommand:
    lesson_id: str
    version: int
    publish_comment: Optional[str] = None

    def validate(self):
        if not self.lesson_id:
            raise DomainValidationError("lesson_id required.")
        if not isinstance(self.version, int) or self.version < 1:
            raise DomainValidationError("version must be integer >= 1.")

@dataclass
class AddContentBlockCommand:
    lesson_version_id: str
    type: str
    position: Optional[int]
    payload: Dict[str, Any]

    def validate(self):
        if not self.lesson_version_id:
            raise DomainValidationError("lesson_version_id required.")
        if self.type not in ("text", "image", "video", "quiz", "exploration_ref"):
            raise DomainValidationError("Invalid content block type.")
        if not isinstance(self.payload, dict):
            raise DomainValidationError("payload must be dict.")

@dataclass
class CreateExplorationCommand:
    title: str
    owner_id: Optional[int]
    language: str = "vi"
    initial_state_name: Optional[str] = None
    schema_version: int = 1

    def validate(self):
        if not self.title or not self.title.strip():
            raise DomainValidationError("Exploration title required.")
        if not isinstance(self.schema_version, int) or self.schema_version < 1:
            raise DomainValidationError("schema_version must be >=1.")

@dataclass
class AddExplorationStateCommand:
    exploration_id: str
    name: str
    content: Dict[str, Any]
    interaction: Dict[str, Any]

    def validate(self):
        if not self.exploration_id:
            raise DomainValidationError("exploration_id required.")
        if not self.name or not self.name.strip():
            raise DomainValidationError("state name required.")
        if not isinstance(self.content, dict) or not isinstance(self.interaction, dict):
            raise DomainValidationError("content and interaction must be dicts.")

@dataclass
class AddExplorationTransitionCommand:
    exploration_id: str
    from_state: str
    to_state: str
    condition: Dict[str, Any]

    def validate(self):
        if not self.exploration_id:
            raise DomainValidationError("exploration_id required.")
        if not self.from_state or not self.to_state:
            raise DomainValidationError("from_state and to_state required.")
        if not isinstance(self.condition, dict):
            raise DomainValidationError("condition must be dict.")