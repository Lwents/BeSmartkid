import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, Iterable, Tuple
from collections import deque

from content.services.exceptions import DomainValidationError, NotFoundError, InvalidOperation
from content.domains.lesson_domain import LessonDomain 


@dataclass
class DomainEvent:
    name: str
    payload: Dict[str, Any]
    occurred_at: datetime = field(default_factory=datetime.now)