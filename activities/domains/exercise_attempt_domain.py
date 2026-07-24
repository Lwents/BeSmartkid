import re
import uuid
from typing import TypedDict, Optional, List, Dict, Any
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from django.utils import timezone

# Removed circular import
from activities.domains.exercise_answer_domain import ExerciseAnswerDomain
from activities.domains.question_domain import QuestionDomain
from activities.domains.exercise_domain import ExerciseDomain


# ---------- Helpers ----------
def now_utc() -> datetime:
    # use timezone-aware datetime to avoid aware/naive subtraction issues
    return timezone.now()

def normalize_text(s: str) -> str:
    s = s or ""
    s = s.strip().lower()
    s = re.sub(r'\s+', ' ', s)
    s = re.sub(r'[^\w\s]', '', s)  # remove punctuation for basic normalization
    return s

def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


class ExerciseAttemptDict(TypedDict):
    id: str
    exercise_id: str
    student_id: Optional[int]
    started_at: datetime
    finished_at: Optional[datetime]
    status: str
    score: Optional[float]
    metadata: Dict[str, Any]


class ExerciseAttemptDomain:
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_FINISHED = "finished"
    STATUS_ABANDONED = "abandoned"

    def __init__(self, id: str, exercise_id: str, student_id: Optional[int],
                 started_at: datetime, finished_at: Optional[datetime], status: str,
                 score: Optional[float], metadata: Dict[str,Any] = None, exercise: Optional[ExerciseDomain] = None):
        self.id = id
        self.exercise_id = exercise_id
        self.student_id = student_id
        self.started_at = started_at
        self.finished_at = finished_at
        self.status = status
        self.score = score
        self.metadata = metadata or {}
        # answers keyed by question_id
        self.answers: Dict[str, ExerciseAnswerDomain] = {}
        # optionally keep a reference to the parent ExerciseDomain to perform scoring
        self.exercise = exercise

    @classmethod
    def from_model(cls, model, exercise_domain: Optional[ExerciseDomain] = None) -> "ExerciseAttemptDomain":
        att = cls(
            id=str(model.id),
            exercise_id=str(getattr(model, 'exercise_id', getattr(model, 'exercise').id)),
            student_id=getattr(model, 'student_id', getattr(model, 'student', None).id if getattr(model, 'student', None) else None),
            started_at=model.started_at,
            finished_at=model.finished_at,
            status=getattr(model, 'status', 'in_progress'),
            score=model.score,
            metadata=getattr(model, 'metadata', {}) or {},
            exercise=exercise_domain
        )
        # load answers if present
        if hasattr(model, 'answers'):
            for a in model.answers.all():
                # Handle answer which can be dict or string
                answer_data = a.answer
                if isinstance(answer_data, str):
                    # If answer is a string (choice ID), convert to dict format for compatibility
                    answer_data = {'selected_choice_id': answer_data}
                elif isinstance(answer_data, list):
                    # If answer is a list (multiple choice IDs), convert to dict format
                    answer_data = {'selected_choice_ids': answer_data}
                elif not isinstance(answer_data, dict):
                    # If answer is neither dict, string, nor list, convert to dict
                    answer_data = {'value': str(answer_data)}
                
                # Extract score from answer if it's a dict, otherwise use correct flag
                score = 0.0
                if isinstance(answer_data, dict):
                    score = answer_data.get('score', 0.0)
                if score == 0.0 and a.correct:
                    score = 1.0
                
                ad = ExerciseAnswerDomain(
                    id=str(a.id),
                    attempt_id=str(a.attempt.id),
                    question_id=str(a.question.id),
                    answer=answer_data,  # Use normalized answer_data
                    correct=a.correct,
                    score=score
                )
                att.answers[ad.question_id] = ad
        return att

    def time_limit_seconds(self) -> Optional[int]:
        return self.metadata.get('time_limit_seconds')

    def time_elapsed_seconds(self) -> float:
        return (now_utc() - self.started_at).total_seconds()

    def time_remaining_seconds(self) -> Optional[float]:
        tl = self.time_limit_seconds()
        if not tl:
            return None
        remaining = tl - self.time_elapsed_seconds()
        return max(0.0, remaining)

    def add_or_update_answer(self, question: QuestionDomain, answer_payload: Dict[str,Any]) -> ExerciseAnswerDomain:
        if self.status != self.STATUS_IN_PROGRESS:
            raise ValueError("Cannot add answer to an attempt that is not in progress.")
        
        # Normalize answer_payload to ensure consistent format
        # Frontend may send string (choice ID) or array (multiple choice IDs) directly
        normalized_answer = answer_payload
        if isinstance(answer_payload, str):
            # Single choice: convert string to dict format
            normalized_answer = {'selected_choice_id': answer_payload}
        elif isinstance(answer_payload, list):
            # Multiple choice: convert array to dict format
            normalized_answer = {'selected_choice_ids': answer_payload}
        elif not isinstance(answer_payload, dict):
            # Other types: wrap in dict
            normalized_answer = {'value': str(answer_payload)}
        
        # scoring via question domain (can handle both normalized and original format)
        score_result = question.score_answer(normalized_answer)
        ans = ExerciseAnswerDomain(
            id=str(uuid.uuid4()),
            attempt_id=self.id,
            question_id=question.id,
            answer=normalized_answer,  # Store normalized format for consistency
            correct=bool(score_result.get('correct')),
            score=float(score_result.get('score', 0.0))
        )
        self.answers[question.id] = ans
        return ans

    def compute_score(self) -> float:
        # total points obtained / total possible points * 100 (percentage)
        if not self.exercise:
            raise ValueError("Attempt must be constructed with exercise domain reference to compute score.")
        total_possible = self.exercise.total_possible_points()
        if total_possible == 0:
            return 0.0
        obtained = sum((a.score or 0.0) for a in self.answers.values())
        pct = (obtained / total_possible) * 100.0
        # round to 2 decimals
        self.score = round(pct, 2)
        return self.score

    def finalize(self) -> Dict[str, Any]:
        # enforce time limit
        tl = self.time_limit_seconds()
        if tl is not None and self.time_elapsed_seconds() > tl:
            # optionally auto-submit remaining questions as blank or partial
            self.status = self.STATUS_FINISHED
            self.finished_at = now_utc()
            # compute score with whatever answers have been provided
            final_score = self.compute_score()
            # store duration into metadata for ranking display
            try:
                delta_sec = max(1, int((self.finished_at - self.started_at).total_seconds()))
                self.metadata["time_taken"] = delta_sec
            except Exception:
                pass
            return {"status": self.status, "score": final_score, "reason": "time_limit_exceeded"}
        # otherwise normal finalize
        self.status = self.STATUS_FINISHED
        self.finished_at = now_utc()
        final_score = self.compute_score()
        # capture time taken (at least 1s) for leaderboard display
        try:
            delta_sec = max(1, int(abs((self.finished_at - self.started_at).total_seconds())))
            self.metadata["time_taken"] = delta_sec
        except Exception:
            pass
        return {"status": self.status, "score": final_score, "reason": "submitted"}

    def summary(self) -> Dict[str, Any]:
        """Return summary suitable for UI: per-question breakdown + overall score."""
        per_q = []
        for q in (self.exercise.questions if self.exercise else []):
            ans = self.answers.get(q.id)
            question_data = {
                "id": q.id,
                "question_id": q.id,
                "prompt": q.prompt,
                "text": q.prompt,  # Alias for frontend compatibility
                "points": q.total_points(),
                "score": q.total_points(),  # Question max score
                "type": q.meta.get('type', 'single'),  # Get question type from meta
                "answer": ans.answer if ans else None,
                "answer_score": ans.score if ans else 0.0,  # Student's answer score
                "correct": ans.correct if ans else False,
                "meta": q.meta or {},
            }
            # Add choices for single/multi choice questions (don't include is_correct for students)
            qtype = q.meta.get('type', 'single')
            if qtype in ('single', 'multi', 'mcq'):
                question_data["choices"] = [
                    {
                        "id": str(c.id),
                        "text": c.text,
                    }
                    for c in q.choices
                ]
                # Add correct answer for display (always show for result view)
                correct_choices = [c for c in q.choices if c.is_correct]
                if qtype == 'single' or qtype == 'mcq':
                    # Single choice: return the text of the correct choice
                    if correct_choices:
                        question_data["correct_answer"] = correct_choices[0].text
                    else:
                        question_data["correct_answer"] = 'N/A'
                else:  # multi
                    # Multiple choice: return comma-separated texts
                    if correct_choices:
                        question_data["correct_answer"] = ", ".join([c.text for c in correct_choices])
                    else:
                        question_data["correct_answer"] = 'N/A'
            # Add other question-specific data
            if qtype == 'fill':
                question_data["blanks"] = q.meta.get('blanks', 1) if isinstance(q.meta.get('blanks'), int) else 1
                # Add correct answer for fill questions
                question_data["correct_answer"] = q.meta.get('correct_answer') or q.meta.get('answer') or 'N/A'
            if qtype == 'match':
                question_data["pairs"] = q.meta.get('pairs', []) if isinstance(q.meta.get('pairs'), list) else []
                # Add correct answer for matching
                pairs = q.meta.get('pairs', [])
                if pairs:
                    question_data["correct_answer"] = ", ".join([f"{p.get('left', '')} → {p.get('right', '')}" for p in pairs])
                else:
                    question_data["correct_answer"] = 'N/A'
            if qtype == 'order':
                question_data["items"] = q.meta.get('items', []) if isinstance(q.meta.get('items'), list) else []
                # Add correct answer for ordering
                items = q.meta.get('items', [])
                if items:
                    question_data["correct_answer"] = ", ".join([f"{idx + 1}. {item}" for idx, item in enumerate(items)])
                else:
                    question_data["correct_answer"] = 'N/A'
            # Add correct answer for boolean questions
            if qtype == 'boolean':
                correct = q.meta.get('correct_answer')
                if correct is True or correct == 'true' or correct == 'True':
                    question_data["correct_answer"] = 'Đúng'
                elif correct is False or correct == 'false' or correct == 'False':
                    question_data["correct_answer"] = 'Sai'
                else:
                    question_data["correct_answer"] = str(correct) if correct else 'N/A'
            
            per_q.append(question_data)
        return {
            "id": self.id,
            "attempt_id": self.id,
            "exercise_id": self.exercise_id,
            "student_id": self.student_id,
            "started_at": self.started_at,
            "deadline_at": self.metadata.get('deadline_at') if self.metadata else None,
            "finished_at": self.finished_at,
            "status": self.status,
            "score": self.score,
            "questions": per_q,
            "answers": {qid: ans.answer for qid, ans in self.answers.items()}  # Include existing answers
        }
