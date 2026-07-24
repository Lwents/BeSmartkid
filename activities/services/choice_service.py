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
# Choice services
# ----------------------
def add_choice(question_id: str, c_domain: ChoiceDomain) -> ChoiceDomain:
    q = QuestionModel.objects.get(id=question_id)
    c = ChoiceModel.objects.create(
        question=q,
        text=c_domain.text,
        is_correct=c_domain.is_correct,
        position=c_domain.position,
    )
    return ChoiceDomain.from_model(c)


def delete_choice(choice_id: str) -> None:
    ChoiceModel.objects.filter(id=choice_id).delete()