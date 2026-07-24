# serializers/activities.py
"""
DRF serializers for activities module (Exercise, Question, Choice, Attempt, Answer).
Philosophy:
- Serializers are thin: convert request <-> validated_data <-> domain objects.
- Domain objects (domain.activities) chứa business rules: scoring, time limit, finalize, etc.
- Use Model Serializers for reading/writing ORM models, and plain Serializers for input-only endpoints.
"""
from typing import Any, Dict, List, Optional
import uuid

from django.apps import apps
from rest_framework import serializers

# import domain objects you made previously
from activities.domains.exercise_domain import (
    ExerciseDomain
)
from activities.domains.question_domain import QuestionDomain
from activities.domains.choice_domain import ChoiceDomain
from activities.domains.exercise_answer_domain import ExerciseAnswerDomain
from activities.domains.exercise_attempt_domain import ExerciseAttemptDomain

# Resolve models dynamically (app label 'activities' assumed)
ExerciseModel = apps.get_model('activities', 'Exercise')
QuestionModel = apps.get_model('activities', 'Question')
ChoiceModel = apps.get_model('activities', 'Choice')
ExerciseAttemptModel = apps.get_model('activities', 'ExerciseAttempt')
ExerciseAnswerModel = apps.get_model('activities', 'ExerciseAnswer')


# -------------------------
# Model serializers (ORM <-> serializer)
# -------------------------
class ChoiceModelSerializer(serializers.ModelSerializer):
    """ModelSerializer for Choice model. Has to_domain() for mapping to ChoiceDomain."""
    id = serializers.UUIDField(required=False)
    question = serializers.PrimaryKeyRelatedField(required=False, allow_null=True, queryset=QuestionModel.objects.all())

    class Meta:
        model = ChoiceModel
        fields = ("id", "question", "text", "is_correct", "position")
        read_only_fields = ("id",)
        extra_kwargs = {
            'question': {'required': False, 'allow_null': True}
        }

    def to_domain(self) -> ChoiceDomain:
        """Convert validated data -> ChoiceDomain."""
        data = self.validated_data
        cid = str(data.get("id") or uuid.uuid4())
        # In nested creation 'question' may be pk; in updates it might be instance
        question_val = data.get("question")
        # Ensure we always use the PK even when DRF gives us a model instance
        question_id = None
        if question_val is not None:
            question_id = str(getattr(question_val, "id", question_val))
        elif self.instance:
            question_id = str(self.instance.question.id)
        return ChoiceDomain(
            id=cid,
            question_id=str(question_id),
            text=data["text"],
            is_correct=bool(data.get("is_correct", False)),
            position=int(data.get("position", 0)),
        )

    @staticmethod
    def from_domain(domain: ChoiceDomain) -> Dict[str, Any]:
        """Convert ChoiceDomain -> primitive dict ready for API response."""
        return domain.to_dict()


class QuestionModelSerializer(serializers.ModelSerializer):
    """ModelSerializer for Question with nested choices support."""
    id = serializers.UUIDField(required=False)
    choices = ChoiceModelSerializer(many=True, required=False)
    meta = serializers.JSONField(required=False)
    exercise = serializers.PrimaryKeyRelatedField(required=False, allow_null=True, queryset=ExerciseModel.objects.all())

    class Meta:
        model = QuestionModel
        fields = ("id", "exercise", "prompt", "meta", "choices")
        read_only_fields = ("id",)
        extra_kwargs = {
            'exercise': {'required': False, 'allow_null': True}
        }

    def to_domain(self) -> QuestionDomain:
        """Convert serializer validated_data -> QuestionDomain (including nested choices)."""
        data = self.validated_data
        qid = str(data.get("id") or uuid.uuid4())
        exercise_val = data.get("exercise")
        exercise_id = None
        if exercise_val is not None:
            exercise_id = str(getattr(exercise_val, "id", exercise_val))
        elif self.instance:
            exercise_id = str(self.instance.exercise.id)
        prompt = data["prompt"]
        meta = data.get("meta", {}) or {}
        choices_raw = self.validated_data.get("choices", [])
        choices: List[ChoiceDomain] = []
        for c in choices_raw:
            # c is dict because nested serializer validated
            cid = str(c.get("id") or uuid.uuid4())
            choices.append(ChoiceDomain(
                id=cid,
                question_id=qid,
                text=c["text"],
                is_correct=bool(c.get("is_correct", False)),
                position=int(c.get("position", 0)),
            ))
        return QuestionDomain(
            id=qid,
            exercise_id=exercise_id,
            prompt=prompt,
            meta=meta,
            choices=choices,
            hints=None
        )

    @staticmethod
    def from_domain(domain: QuestionDomain) -> Dict[str, Any]:
        """QuestionDomain -> dict (for API responses)."""
        d = domain.to_dict()
        # add choices listing
        d["choices"] = [c.to_dict() for c in domain.choices]
        return d


class ExerciseModelSerializer(serializers.ModelSerializer):
    """ModelSerializer for Exercise with nested questions."""
    id = serializers.UUIDField(required=False)
    questions = QuestionModelSerializer(many=True, required=False)
    settings = serializers.JSONField(required=False)

    class Meta:
        model = ExerciseModel
        fields = ("id", "lesson", "title", "type", "published", "settings", "questions")
        read_only_fields = ("id",)
        extra_kwargs = {
            'lesson': {'required': False, 'allow_null': True},
            'type': {'required': False},  # Allow type to be optional on update
            'published': {'required': False}  # Allow published to be optional on update
        }

    def to_domain(self) -> ExerciseDomain:
        """Convert validated_data -> ExerciseDomain (including nested questions)."""
        data = self.validated_data
        eid = str(data.get("id") or (self.instance.id if self.instance else uuid.uuid4()))
        lesson_val = data.get("lesson")
        lesson_id = None
        if lesson_val is not None:
            # lesson_val may be a Lesson instance; use its PK instead of __str__()
            lesson_id = str(getattr(lesson_val, "id", lesson_val))
        elif self.instance and hasattr(self.instance, 'lesson') and self.instance.lesson:
            lesson_id = str(self.instance.lesson.id)
        title = data.get("title") or (self.instance.title if self.instance else "")
        # Get type from data, or fallback to instance type, or default to 'mcq'
        typ = data.get("type") or (self.instance.type if self.instance else "mcq")
        settings = data.get("settings", {}) or {}
        questions_supplied = "questions" in self.validated_data
        questions_raw = self.validated_data.get("questions", [])
        q_domains: List[QuestionDomain] = []
        existing_qids = set()
        if self.instance and hasattr(self.instance, "questions"):
            try:
                existing_qids = {str(qm.id) for qm in self.instance.questions.all()}
            except Exception:
                existing_qids = set()
        # A partial update such as {"published": true} must not be interpreted
        # as "replace all questions with an empty list".  The service performs
        # an intentional full sync, so retain the existing nested objects when
        # the questions field was omitted from a PATCH request.
        if self.instance and not questions_supplied:
            q_domains = [
                QuestionDomain.from_model(question)
                for question in self.instance.questions.prefetch_related("choices").all()
            ]

        for q in questions_raw:
            incoming_qid = q.get("id")
            if incoming_qid and str(incoming_qid) in existing_qids:
                qid = str(incoming_qid)
            else:
                qid = str(incoming_qid or uuid.uuid4())
            # choices inside q already validated
            choices_raw = q.get("choices", [])
            c_domains = [
                ChoiceDomain(
                    id=str(c.get("id") or uuid.uuid4()),
                    question_id=qid,
                    text=c["text"],
                    is_correct=bool(c.get("is_correct", False)),
                    position=int(c.get("position", 0)),
                ) for c in choices_raw
            ]
            q_domains.append(QuestionDomain(
                id=qid,
                exercise_id=eid,
                prompt=q["prompt"],
                meta=q.get("meta", {}) or {},
                choices=c_domains,
                hints=None
            ))
        # Get published from validated_data if provided, otherwise from instance
        published = data.get("published")
        if published is None:
            published = getattr(self.instance, "published", False) if self.instance else False
        else:
            published = bool(published)
        
        return ExerciseDomain(
            id=eid,
            lesson_id=lesson_id,
            title=title,
            type=typ,
            settings=settings,
            questions=q_domains,
            published=published,
            created_on=getattr(self.instance, "created_on", None) if self.instance else None,
            updated_on=getattr(self.instance, "updated_on", None) if self.instance else None
        )

    @staticmethod
    def from_domain(domain: ExerciseDomain) -> Dict[str, Any]:
        """Convert ExerciseDomain -> dict for API responses."""
        return {
            "id": domain.id,
            "lesson": domain.lesson_id,
            "title": domain.title,
            "type": domain.type,
            "published": domain.published,  # Include published status in response
            "settings": domain.settings,
            # include full question payloads
            "questions": [QuestionModelSerializer.from_domain(q) for q in domain.questions],
        }


# -------------------------
# Attempt / Answer serializers
# -------------------------
class ExerciseAnswerModelSerializer(serializers.ModelSerializer):
    """Serializer for ExerciseAnswer model. Use to_domain/from_domain to convert to domain."""
    id = serializers.UUIDField(required=False)
    answer = serializers.JSONField()
    correct = serializers.BooleanField(required=False, allow_null=True)
    # keep score in answer JSON or top-level if you prefer
    class Meta:
        model = ExerciseAnswerModel
        fields = ("id", "attempt", "question", "answer", "correct")
        read_only_fields = ("id",)

    def to_domain(self) -> ExerciseAnswerDomain:
        data = self.validated_data
        aid = str(data.get("id") or uuid.uuid4())
        attempt_val = data.get("attempt")
        attempt_id = str(attempt_val) if attempt_val is not None else (str(self.instance.attempt.id) if self.instance else None)
        question_val = data.get("question")
        question_id = str(question_val) if question_val is not None else (str(self.instance.question.id) if self.instance else None)
        answer_payload = data.get("answer", {}) or {}
        correct = data.get("correct", None)
        score = None
        if isinstance(answer_payload, dict) and "score" in answer_payload:
            # some use-cases store per-answer score inside answer JSON
            try:
                score = float(answer_payload.get("score"))
            except Exception:
                score = None
        return ExerciseAnswerDomain(
            id=aid,
            attempt_id=attempt_id,
            question_id=question_id,
            answer=answer_payload,
            correct=correct,
            score=score
        )

    @staticmethod
    def from_domain(domain: ExerciseAnswerDomain) -> Dict[str, Any]:
        return domain.to_dict()


class ExerciseAttemptModelSerializer(serializers.ModelSerializer):
    """ModelSerializer for ExerciseAttempt (read-heavy). Embeds answers and exercise summary when available."""
    id = serializers.UUIDField(required=False)
    exercise = ExerciseModelSerializer(read_only=True)
    answers = ExerciseAnswerModelSerializer(many=True, required=False)
    metadata = serializers.JSONField(required=False)

    class Meta:
        model = ExerciseAttemptModel
        fields = ("id", "exercise", "student", "started_at", "finished_at", "score", "metadata", "answers")
        read_only_fields = ("id", "started_at", "finished_at")

    @classmethod
    def from_domain(cls, attempt: ExerciseAttemptDomain) -> Dict[str, Any]:
        """
        Convert ExerciseAttemptDomain -> dict (for API responses).
        This returns summary with per-question breakdown using attempt.summary().
        """
        summary = attempt.summary()
        # ensure proper JSON-serializable values (datetimes kept)
        return summary


# -------------------------
# Use-case (input-only) serializers
# -------------------------
class StartAttemptSerializer(serializers.Serializer):
    """Input serializer for starting an attempt. Will be converted into domain by service layer."""
    exercise_id = serializers.UUIDField()
    student_id = serializers.IntegerField(required=False, allow_null=True)

    def create_attempt_domain(self, exercise_domain: ExerciseDomain) -> ExerciseAttemptDomain:
        """
        Convert validated request -> ExerciseAttemptDomain by using the ExerciseDomain factory.
        The view/service should fetch ExerciseModel -> ExerciseDomain first, call this, then persist.
        """
        student_id = self.validated_data.get("student_id")
        # Delegates business rules (max attempts, time limit) to ExerciseDomain.create_attempt(...)
        return exercise_domain.create_attempt(student_id=student_id)


class SubmitAnswerSerializer(serializers.Serializer):
    """
    Input serializer for submitting/updating one answer.
    Payload shape:
    {
      "attempt_id": "<uuid>",
      "question_id": "<uuid>",
      "answer": {...}  # free-form, domain.question.score_answer will interpret
    }
    """
    attempt_id = serializers.UUIDField()
    question_id = serializers.UUIDField()
    answer = serializers.JSONField()

    def to_answer_domain(self, attempt_domain: ExerciseAttemptDomain, question_domain: QuestionDomain) -> ExerciseAnswerDomain:
        """
        Convert validated input -> ExerciseAnswerDomain by calling domain logic (scoring).
        - attempt_domain: domain object for current attempt (must be loaded by view/service)
        - question_domain: domain object for the question being answered
        Returns ExerciseAnswerDomain already scored (score, correct).
        """
        # Basic structural check (optionally)
        if self.validated_data["question_id"] != question_domain.id:
            # If the API caller passed mismatching data; service should catch it before
            raise serializers.ValidationError("question_id does not match given QuestionDomain.")

        # Delegate scoring to domain: attempt.add_or_update_answer uses QuestionDomain.score_answer internally
        answer_payload = self.validated_data["answer"]
        # This will update attempt_domain.answers internally (in-memory). Persisting is service's job.
        answer_domain = attempt_domain.add_or_update_answer(question_domain, answer_payload)
        return answer_domain


class FinalizeAttemptSerializer(serializers.Serializer):
    """
    Input for finalize endpoint. (Very small; finalize typically needs only attempt_id.)
    Optionally client may send 'force' to override some checks (e.g., instructor finalize).
    """
    attempt_id = serializers.UUIDField()
    force = serializers.BooleanField(default=False)

    def finalize(self, attempt_domain: ExerciseAttemptDomain, force: bool = False) -> Dict[str, Any]:
        """
        Call domain finalize. If force=True, service layer may bypass some business rules
        (example: allow finalize after time limit or allow instructor override).
        """
        if force:
            # Example: if forcing, simply set finished and compute
            attempt_domain.status = attempt_domain.STATUS_FINISHED
            attempt_domain.finished_at = attempt_domain.finished_at or __import__("datetime").datetime.utcnow()
            attempt_domain.compute_score()
            return {"status": attempt_domain.status, "score": attempt_domain.score, "reason": "forced_by_user"}
        return attempt_domain.finalize()


# -------------------------
# Small helper functions for mapping Domain -> API response
# -------------------------
def exercise_domain_to_response(domain: ExerciseDomain) -> Dict[str, Any]:
    """Return a JSON-serializable representation of ExerciseDomain for API responses."""
    return ExerciseModelSerializer.from_domain(domain)


def attempt_domain_to_response(attempt_domain: ExerciseAttemptDomain) -> Dict[str, Any]:
    """Return attempt summary as API-friendly dictionary (uses attempt_domain.summary())."""
    # attempt_domain.summary() already returns a serializable-ish structure
    summary = attempt_domain.summary()
    # Convert datetimes to ISO strings if necessary in your renderer — optional here:
    # for clarity we leave datetimes as-is and let DRF handle them, or transform here.
    return summary
