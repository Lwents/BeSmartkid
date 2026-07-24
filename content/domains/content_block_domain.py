import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, Iterable, Tuple, TYPE_CHECKING
from collections import deque

from content.services.exceptions import DomainValidationError, NotFoundError, InvalidOperation
from content.domains.value_objects import AddContentBlockCommand

if TYPE_CHECKING:
    from content.domains.lesson_version_domain import LessonVersionDomain



class ContentBlockDomain:
    """
    Supported types: text, image, video, quiz, exploration_ref
    payload schema rules enforced here.
    """

    VALID_TYPES = ("text", "image", "video", "quiz", "exploration_ref")

    # Example max limits
    MAX_TEXT_LENGTH = 5000
    MAX_MEDIA_SIZE_BYTES = 10 * 1024 * 1024  # 10MB

    def __init__(self, lesson_version_id: str, type: str, position: int = 0, payload: Optional[Dict[str, Any]] = None, id: Optional[str] = None):
        self.id = id or str(uuid.uuid4())
        self.lesson_version_id = lesson_version_id
        self.type = type
        self.position = int(position)
        self.payload = payload or {}
        self.validate_basic()

    def validate_basic(self):
        if not self.lesson_version_id:
            raise DomainValidationError("ContentBlock.lesson_version_id required.")
        if self.type not in self.VALID_TYPES:
            raise DomainValidationError(f"Invalid ContentBlock type: {self.type}")
        if self.position < 0:
            raise DomainValidationError("ContentBlock.position must be >= 0")

    def validate_payload(self):
        """Validate payload according to type. Raise DomainValidationError if invalid."""
        # text
        if self.type == "text":
            txt = self.payload.get("text", "")
            if not isinstance(txt, str) or not txt.strip():
                raise DomainValidationError("Text block must contain non-empty 'text'.")
            if len(txt) > self.MAX_TEXT_LENGTH:
                raise DomainValidationError("Text block too long.")
            # optional tts_text allowed
        # image/video
        elif self.type in ("image", "video"):
            url = self.payload.get("url")
            storage_id = self.payload.get("storage_id")
            if not url and not storage_id:
                raise DomainValidationError(f"{self.type} block must include 'url' or 'storage_id'.")
            # Optionally validate mime/size if provided
            size = self.payload.get("size_bytes")
            if size is not None:
                try:
                    size = int(size)
                    if size > self.MAX_MEDIA_SIZE_BYTES:
                        raise DomainValidationError(f"{self.type} exceeds max allowed size.")
                except ValueError:
                    raise DomainValidationError("size_bytes must be an integer.")
        # quiz
        elif self.type == "quiz":
            # payload expected: {"questions": [ {..} ], "max_score": int}
            questions = self.payload.get("questions")
            if not isinstance(questions, list) or len(questions) == 0:
                raise DomainValidationError("Quiz must contain at least one question.")
            for idx, q in enumerate(questions):
                if not isinstance(q, dict):
                    raise DomainValidationError(f"Quiz question[{idx}] must be an object.")
                if "type" not in q or q["type"] not in ("multiple_choice", "short_answer"):
                    raise DomainValidationError(f"Quiz question[{idx}] invalid or missing type.")
                # For multiple_choice, require options and one correct index
                if q["type"] == "multiple_choice":
                    opts = q.get("options")
                    if not isinstance(opts, list) or len(opts) < 2:
                        raise DomainValidationError(f"multiple_choice question[{idx}] must have >=2 options.")
                    correct = q.get("correct_index")
                    if not isinstance(correct, int) or not (0 <= correct < len(opts)):
                        raise DomainValidationError(f"multiple_choice question[{idx}] has invalid correct_index.")
        # exploration reference
        elif self.type == "exploration_ref":
            exploration_id = self.payload.get("exploration_id")
            if not exploration_id:
                raise DomainValidationError("exploration_ref must include exploration_id.")
            # optionally start_state name
        else:
            raise DomainValidationError("Unsupported content block type.")
        return True

    def to_dict(self):
        return {"id": self.id, "lesson_version_id": self.lesson_version_id, "type": self.type, "position": self.position, "payload": self.payload}

    @classmethod
    def from_model(cls, model):
        return cls(lesson_version_id=str(getattr(model,'lesson_version_id', None) or ""),
                   type=model.type, position=model.position, payload=model.payload, id=str(model.id))
    

class CreateContentBlockDomain:
    def __init__(self, version: "LessonVersionDomain"):
        self.version = version

    def execute(self, command: AddContentBlockCommand) -> ContentBlockDomain:
        command.validate()
        self.version.validate()  # Ensure version is valid
        new_block = self.version.add_content_block(type=command.type, position=command.position, payload=command.payload)
        self.version.validate_content()  # Post-validation
        return new_block

class UpdateContentBlockDomain:
    def __init__(self, version: "LessonVersionDomain"):
        self.version = version

    def execute(self, block_id: str, new_payload: Dict[str, Any]) -> ContentBlockDomain:
        if not block_id:
            raise DomainValidationError("block_id required.")
        if not isinstance(new_payload, dict):
            raise DomainValidationError("new_payload must be dict.")
        self.version.validate()
        updated_block = self.version.update_content_block(block_id, new_payload)
        self.version.validate_content()
        return updated_block

class ReorderContentBlocksDomain:
    def __init__(self, version: "LessonVersionDomain"):
        self.version = version

    def execute(self, new_order: List[str]) -> List[ContentBlockDomain]:
        if not isinstance(new_order, list) or not new_order:
            raise DomainValidationError("new_order must be non-empty list of block IDs.")
        self.version.validate()
        self.version.reorder_content_blocks(new_order)
        self.version.validate_content()
        return self.version.content_blocks