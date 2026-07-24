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


class ExerciseAnswerDict(TypedDict):
    id: str
    attempt_id: str
    question_id: str
    answer: Dict[str, Any]
    correct: Optional[bool]
    score: Optional[float]


class ExerciseAnswerDomain:
    def __init__(self, id: str, attempt_id: str, question_id: str, answer: Dict[str,Any],
                 correct: Optional[bool]=None, score: Optional[float]=None, created_at: Optional[datetime]=None):
        self.id = id
        self.attempt_id = attempt_id
        self.question_id = question_id
        self.answer = answer
        self.correct = correct
        self.score = score
        self.created_at = created_at or now_utc()

    def to_dict(self) -> ExerciseAnswerDict:
        return {
            "id": self.id,
            "attempt_id": self.attempt_id,
            "question_id": self.question_id,
            "answer": self.answer,
            "correct": self.correct,
            "score": self.score
        }