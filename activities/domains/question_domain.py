import re
import uuid
from typing import TypedDict, Optional, List, Dict, Any, TYPE_CHECKING
from datetime import datetime, timedelta
from difflib import SequenceMatcher

if TYPE_CHECKING:
    from activities.domains.choice_domain import ChoiceDomain


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


class QuestionDict(TypedDict):
    id: str
    exercise_id: str
    prompt: str
    meta: Dict[str, Any]  # e.g., difficulty, time_limit, accepted_answers, multiple:bool, points: float


class QuestionDomain:
    ALLOWED_TYPES = {"mcq", "short_answer", "matching"}

    def __init__(self, id: str, exercise_id: str, prompt: str, meta: Optional[Dict[str, Any]] = None,
                 choices: Optional[List["ChoiceDomain"]] = None, hints: Optional[List[str]] = None):
        self.id = id
        self.exercise_id = exercise_id
        self.prompt = prompt
        self.meta = meta or {}
        self.choices = choices or []
        self.hints = hints or []

    @classmethod
    def from_model(cls, model) -> "QuestionDomain":
        from activities.domains.choice_domain import ChoiceDomain
        choices = [ChoiceDomain.from_model(c) for c in getattr(model, 'choices').all()] if hasattr(model, 'choices') else []
        hints = [h.text for h in getattr(model, 'hints').all()] if hasattr(model, 'hints') else []
        return cls(
            id=str(model.id),
            exercise_id=str(getattr(model, 'exercise_id', getattr(model, 'exercise').id)),
            prompt=model.prompt,
            meta=model.meta or {},
            choices=choices,
            hints=hints
        )

    def to_dict(self) -> QuestionDict:
        return {
            "id": self.id,
            "exercise_id": self.exercise_id,
            "prompt": self.prompt,
            "meta": self.meta
        }

    def validate(self):
        qtype = self.meta.get('type') or self.meta.get('question_type') or self.meta.get('format')
        # if not set, fallback: exercise-level type should determine it. Here we just check basic.
        if 'type' in self.meta:
            if self.meta['type'] not in self.ALLOWED_TYPES:
                raise ValueError(f"Invalid question type: {self.meta['type']}")
        # if mcq ensure at least 2 choices
        if self.meta.get('type') == 'mcq' and len(self.choices) < 2:
            raise ValueError("MCQ must have at least two choices.")
        # points default
        if 'points' in self.meta:
            if not isinstance(self.meta['points'], (int, float)):
                raise ValueError("meta.points must be numeric if present.")
        else:
            self.meta['points'] = float(self.meta.get('points', 1.0))

    def total_points(self) -> float:
        return float(self.meta.get('points', 1.0))

    # --- Business rule: score an answer for this question ---
    def score_answer(self, answer_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        answer_payload: format varies by question type.
        Returns: {'score': float, 'correct': bool, 'explanation': Optional[str]}
        """
        qtype = self.meta.get('type', 'mcq')
        points = self.total_points()
        
        # Map 'single' and 'multi' to 'mcq' for compatibility
        if qtype in ('single', 'multi'):
            qtype = 'mcq'
            # For 'multi', set multiple flag
            if self.meta.get('type') == 'multi':
                self.meta['multiple'] = True

        if qtype == 'mcq':
            # Answer payload conventions:
            # - single choice: {'selected_choice_id': 'uuid'}
            # - multiple: {'selected_choice_ids': ['uuid1','uuid2']}
            multiple = bool(self.meta.get('multiple', False))
            correct_choice_ids = {c.id for c in self.choices if c.is_correct}
            if multiple:
                # Support both formats: {'selected_choice_ids': [...]} or direct array
                selected_ids = None
                # Check if answer_payload is a dict first
                if isinstance(answer_payload, dict):
                    selected_ids = answer_payload.get('selected_choice_ids')
                # If not found in dict or not a dict, try direct array
                if selected_ids is None:
                    # Try direct array (frontend may send array directly)
                    if isinstance(answer_payload, list):
                        selected_ids = answer_payload
                    else:
                        selected_ids = []
                
                selected = {str(sid) for sid in selected_ids}
                if not selected:
                    return {"score": 0.0, "correct": False, "explanation": "No choice selected."}
                
                # Convert correct_choice_ids to strings for comparison
                correct_choice_ids_str = {str(cid) for cid in correct_choice_ids}
                # partial credit: (#correct_selected / #correct_total) - (#incorrect_selected / #choices)
                correct_selected = len(selected & correct_choice_ids_str)
                incorrect_selected = len(selected - correct_choice_ids_str)
                if len(correct_choice_ids_str) == 0:
                    base = 0.0
                else:
                    base = correct_selected / len(correct_choice_ids_str)
                penalty = incorrect_selected / max(1, len(self.choices))
                raw = max(0.0, base - penalty * (1.0 if self.meta.get('penalize_wrong', False) else 0.0))
                score = round(points * raw, 4)
                correct_flag = (correct_selected == len(correct_choice_ids_str) and incorrect_selected == 0)
                return {"score": score, "correct": correct_flag, "explanation": None}
            else:
                # Support both formats: {'selected_choice_id': '...'} or direct string/ID
                selected = None
                # Check if answer_payload is a dict first
                if isinstance(answer_payload, dict):
                    selected = answer_payload.get('selected_choice_id')
                # If not found in dict or not a dict, try direct value
                if selected is None:
                    # Try direct value (frontend may send choice ID directly)
                    if isinstance(answer_payload, str):
                        selected = answer_payload
                    elif isinstance(answer_payload, (list, tuple)) and len(answer_payload) > 0:
                        # If it's a list, take first element
                        selected = str(answer_payload[0])
                    elif not isinstance(answer_payload, dict):
                        # If answer_payload is not a dict, treat it as the choice ID
                        selected = str(answer_payload)
                
                if selected is None:
                    return {"score": 0.0, "correct": False, "explanation": "No choice selected."}
                
                # Convert to string for comparison
                selected = str(selected)
                correct_choice_ids_str = {str(cid) for cid in correct_choice_ids}
                
                if selected in correct_choice_ids_str:
                    return {"score": points, "correct": True, "explanation": None}
                else:
                    if self.meta.get('negative_marking', False):
                        # simple negative marking full penalty
                        return {"score": -points, "correct": False, "explanation": "Wrong answer, negative marking applied."}
                    return {"score": 0.0, "correct": False, "explanation": None}

        elif qtype == 'short_answer':
            # meta may contain 'accepted_answers': list[str] OR regex patterns
            # Support both dict format and direct string
            if isinstance(answer_payload, dict):
                text = normalize_text(answer_payload.get('text', ''))
            elif isinstance(answer_payload, str):
                text = normalize_text(answer_payload)
            else:
                text = normalize_text(str(answer_payload))
            accepted = self.meta.get('accepted_answers', [])
            threshold = float(self.meta.get('similarity_threshold', 0.85))
            # exact or regex match
            for candidate in accepted:
                if candidate.startswith('re:'):
                    pattern = candidate[3:]
                    if re.search(pattern, text):
                        return {"score": points, "correct": True, "explanation": None}
                else:
                    cand_norm = normalize_text(candidate)
                    if cand_norm == text:
                        return {"score": points, "correct": True, "explanation": None}
                    if similarity(cand_norm, text) >= threshold:
                        # partial acceptance: give full points (configurable)
                        return {"score": points, "correct": True, "explanation": "Fuzzy match accepted."}
            # not accepted
            return {"score": 0.0, "correct": False, "explanation": "Answer doesn't match accepted responses."}

        elif qtype == 'matching':
            # meta: expects 'pairs' or choices representing left/right stored separately.
            # answer_payload: {'pairs': [{'left_id': 'L1', 'right_id': 'R3'}, ...]}
            correct_pairs = self.meta.get('correct_pairs', {})  # left_id->right_id
            pairs = []
            if isinstance(answer_payload, dict):
                pairs = answer_payload.get('pairs', [])
            elif isinstance(answer_payload, list):
                pairs = answer_payload
            submitted = {p['left_id']: p['right_id'] for p in pairs if isinstance(p, dict) and 'left_id' in p and 'right_id' in p}
            if not submitted:
                return {"score": 0.0, "correct": False, "explanation": "No pairs submitted."}
            total = len(correct_pairs)
            correct_count = sum(1 for l, r in submitted.items() if correct_pairs.get(l) == r)
            score = round(points * (correct_count / max(1, total)), 4)
            correct_flag = (correct_count == total)
            return {"score": score, "correct": correct_flag, "explanation": f"{correct_count}/{total} correct."}

        else:
            raise NotImplementedError(f"Scoring not implemented for question type {qtype}")