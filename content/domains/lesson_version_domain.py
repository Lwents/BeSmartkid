import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, Iterable, Tuple, TYPE_CHECKING
from collections import deque

from content.services.exceptions import DomainValidationError, NotFoundError, InvalidOperation
from content.domains.content_block_domain import ContentBlockDomain
from content.domains.value_objects import CreateLessonVersionCommand

if TYPE_CHECKING:
    from content.domains.lesson_domain import LessonDomain



class LessonVersionDomain:
    VALID_STATUSES = ("draft", "review", "published", "archived")

    def __init__(self,
                 lesson_id: str,
                 version: int,
                 status: str = "draft",
                 author_id: Optional[int] = None,
                 content: Optional[Dict[str, Any]] = None,
                 change_summary: Optional[str] = None,
                 created_at: Optional[datetime] = None,
                 id: Optional[str] = None,
                 published_at: Optional[datetime] = None):
        self.id = id or str(uuid.uuid4())
        self.lesson_id = lesson_id
        self.version = int(version)
        self.status = status
        self.author_id = author_id
        self.content = content or {}  # canonical structured content (e.g., content_blocks list)
        self.change_summary = change_summary
        self.created_at = created_at or datetime.now()
        self.published_at = published_at
        self.content_blocks: List["ContentBlockDomain"] = []
        self.validate()

    def validate(self):
        if not self.lesson_id:
            raise DomainValidationError("LessonVersion.lesson_id required.")
        if self.version < 1:
            raise DomainValidationError("LessonVersion.version must be >= 1.")
        if self.status not in self.VALID_STATUSES:
            raise DomainValidationError(f"Invalid LessonVersion.status: {self.status}")

    def validate_content(self):
        # Basic business rules for content:
        # - If content_blocks present, must be list and each block must validate.
        cb_list = self.content.get("content_blocks") or []
        if cb_list and not isinstance(cb_list, list):
            raise DomainValidationError("content_blocks must be a list.")
        # Validate each content block using ContentBlockDomain rules
        validated_blocks = []
        for idx, cb in enumerate(cb_list):
            # cb expected to be a dict with type/payload/position
            if not isinstance(cb, dict):
                raise DomainValidationError(f"content_blocks[{idx}] must be dict.")
            block = ContentBlockDomain(lesson_version_id=self.lesson_id, type=cb.get("type"), position=cb.get("position", idx), payload=cb.get("payload", {}))
            block.validate_payload()  # may raise
            validated_blocks.append(block)
        # After validation, store domain content blocks (in-memory)
        self.content_blocks = validated_blocks
        # Domain rule: when publishing, must have at least one non-empty content block
        return True

    def add_content_block(self, block: "ContentBlockDomain"):
        if not isinstance(block, ContentBlockDomain):
            raise DomainValidationError("add_content_block expects ContentBlockDomain.")
        # insert at position and normalize
        self.content_blocks.append(block)
        self._normalize_content_positions()

    def _normalize_content_positions(self):
        self.content_blocks.sort(key=lambda b: b.position)
        for idx, b in enumerate(self.content_blocks):
            b.position = idx

    def to_dict(self):
        return {
            "id": self.id,
            "lesson_id": self.lesson_id,
            "version": self.version,
            "status": self.status,
            "author_id": self.author_id,
            "content": self.content,
            "change_summary": self.change_summary,
            "created_at": self.created_at,
            "published_at": self.published_at,
            "content_blocks": [b.to_dict() for b in self.content_blocks]
        }

    @classmethod
    def from_model(cls, model):
        lv = cls(lesson_id=str(model.lesson.id) if getattr(model,'lesson',None) else str(getattr(model,'lesson_id',None) or ""),
                 version=model.version, status=model.status, author_id=(model.author.id if getattr(model,'author',None) else None),
                 content=model.content, change_summary=getattr(model,'change_summary', None),
                 created_at=getattr(model,'created_at', None), id=str(model.id), published_at=getattr(model,'published_at',None))
        if hasattr(model, "content_blocks_prefetched") and model.content_blocks_prefetched:
            for cb_m in model.content_blocks_prefetched:
                lv.content_blocks.append(ContentBlockDomain.from_model(cb_m))
        return lv
    

class CreateLessonVersionDomain:
    """
    Domain service for creating a new lesson version.
    Mimics Oppia use case: Takes a command, validates, creates via aggregate, returns the version.
    In large systems, this would be called by a handler/application service.
    """
    def __init__(self, lesson: "LessonDomain"):
        self.lesson = lesson

    def execute(self, command: "CreateLessonVersionCommand") -> "LessonVersionDomain":
        command.validate()
        # Business rules: Can't create if lesson not valid
        self.lesson.validate()
        # Create via aggregate (DDD style: aggregate handles its entities)
        new_version = self.lesson.create_version(
            author_id=command.author_id,
            content=command.content,
            change_summary=command.change_summary
        )
        # Additional large-system features: Emit domain event (placeholder)
        # e.g., DomainEvents.raise(LessonVersionCreatedEvent(new_version))
        # Audit/log: Could persist here or in repo
        return new_version

class UpdateLessonVersionDomain:
    """
    Domain service for updating an existing lesson version.
    Mimics Oppia update use case: Only allows updates on non-published versions.
    Validates changes, updates content, bumps timestamps.
    """
    def __init__(self, lesson: "LessonDomain"):
        self.lesson = lesson

    def execute(self, version: int, author_id: Optional[int], new_content: Dict[str, Any], change_summary: Optional[str] = None) -> "LessonVersionDomain":
        # Get version via aggregate
        target_version = self.lesson.get_version(version)
        # Business rules: Can't update published versions (force new version instead, like Oppia revisions)
        if target_version.status == "published":
            raise InvalidOperation("Cannot update a published version; create a new one instead.")
        # Validate new content
        if not isinstance(new_content, dict):
            raise DomainValidationError("new_content must be a dict.")
        if not new_content:
            raise DomainValidationError("new_content must not be empty.")
        # Merge or replace content (assuming replace for simplicity; could diff like Oppia)
        target_version.content = new_content
        target_version.change_summary = change_summary or target_version.change_summary
        target_version.author_id = author_id or target_version.author_id
        target_version.updated_at = datetime.now()
        # Re-validate content
        target_version.validate_content()
        # Status transition: Move to 'review' if was 'draft'
        if target_version.status == "draft":
            target_version.status = "review"
        # Emit event (placeholder)
        # DomainEvents.raise(LessonVersionUpdatedEvent(target_version))
        return target_version

class ChangeVersionStatusDomain:
    """
    Domain service for changing version status (e.g., publish/unpublish).
    Mimics Oppia publish workflow: Handles transitions with rules, updates aggregate.
    Supports publish_comment for audit.
    """
    VALID_TRANSITIONS = {
        "draft": ["review"],
        "review": ["published", "draft"],
        "published": ["review"]  # Unpublish
    }

    def __init__(self, lesson: "LessonDomain"):
        self.lesson = lesson

    def execute(self, version: int, new_status: str, publish_comment: Optional[str] = None) -> "LessonVersionDomain":
        if new_status not in ("draft", "review", "published"):
            raise DomainValidationError("Invalid new_status.")
        target_version = self.lesson.get_version(version)
        current_status = target_version.status
        # Enforce transitions (business rule, like state machines in Oppia)
        if new_status not in self.VALID_TRANSITIONS.get(current_status, []):
            raise InvalidOperation(f"Cannot transition from {current_status} to {new_status}.")
        if new_status == "published":
            # Use aggregate's publish method for invariants
            self.lesson.publish_version(version)
            target_version.change_summary = publish_comment or target_version.change_summary
        elif new_status == "review" and current_status == "published":
            # Unpublish
            self.lesson.unpublish_all_versions()  # Since only one published at a time
            target_version.change_summary = publish_comment or "Unpublished"
        else:
            # Simple status change
            target_version.status = new_status
            target_version.change_summary = publish_comment or target_version.change_summary
            target_version.updated_at = datetime.now()
            if new_status != "published":
                target_version.published_at = None
        # Update lesson published flag via aggregate
        self.lesson.published = self.lesson.has_published_version()
        # Emit event (placeholder)
        # DomainEvents.raise(VersionStatusChangedEvent(target_version, new_status))
        return target_version