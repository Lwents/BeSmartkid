import re
import uuid
from typing import TypedDict, Optional, List, Dict, Any
from datetime import datetime, timedelta
from difflib import SequenceMatcher


# ---------- Helpers ----------
def now_utc() -> datetime:
    return datetime.utcnow()

def normalize_text(s: str) -> str:
    s = s or ""
    s = s.strip().lower()
    s = re.sub(r'\s+', ' ', s)
    s = re.sub(r'[^\w\s]', '', s)  # remove punctuation for basic normalization
    return s

def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()



class ChoiceDict(TypedDict):
    id: str
    question_id: str
    text: str
    is_correct: bool
    position: int


class ChoiceDomain:
    def __init__(self, id: str, question_id: str, text: str, is_correct: bool = False, position: int = 0):
        self.id = id
        self.question_id = question_id
        self.text = text
        self.is_correct = is_correct
        self.position = position

    @classmethod
    def from_model(cls, model) -> "ChoiceDomain":
        return cls(
            id=str(model.id),
            question_id=str(getattr(model, 'question_id', getattr(model, 'question').id)),
            text=model.text,
            is_correct=bool(model.is_correct),
            position=int(model.position or 0)
        )

    def to_dict(self) -> ChoiceDict:
        return {
            "id": self.id,
            "question_id": self.question_id,
            "text": self.text,
            "is_correct": self.is_correct,
            "position": self.position
        }