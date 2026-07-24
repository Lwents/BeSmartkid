from typing import List, Dict, Any, Tuple
from django.db import transaction
from django.db.models import Avg
from django.apps import apps
import csv, io

# Domain imports
from activities.domains.exercise_domain import ExerciseDomain
from activities.domains.question_domain import QuestionDomain
from activities.domains.choice_domain import ChoiceDomain
from activities.domains.exercise_attempt_domain import ExerciseAttemptDomain
from activities.domains.exercise_answer_domain import ExerciseAnswerDomain

# Models
ExerciseModel = apps.get_model("activities", "Exercise")
QuestionModel = apps.get_model("activities", "Question")
ChoiceModel = apps.get_model("activities", "Choice")
ExerciseAttemptModel = apps.get_model("activities", "ExerciseAttempt")
ExerciseAnswerModel = apps.get_model("activities", "ExerciseAnswer")



# ----------------------
# Question services
# ----------------------
def add_question(exercise_id: str, q_domain: QuestionDomain) -> QuestionDomain:
    with transaction.atomic():
        ex = ExerciseModel.objects.get(id=exercise_id)
        q = QuestionModel.objects.create(
            exercise=ex, prompt=q_domain.prompt, meta=q_domain.meta or {}
        )
        for choice_domain in q_domain.choices:
            ChoiceModel.objects.create(
                question=q,
                text=choice_domain.text,
                is_correct=choice_domain.is_correct,
                position=choice_domain.position,
            )
        return QuestionDomain.from_model(q)


def delete_question(question_id: str) -> None:
    QuestionModel.objects.filter(id=question_id).delete()
