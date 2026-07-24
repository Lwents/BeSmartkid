import uuid
import json
from datetime import timedelta

import pytest
import factory
from django.apps import apps
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

# Models
Exercise = apps.get_model("activities", "Exercise")
Question = apps.get_model("activities", "Question")
Choice = apps.get_model("activities", "Choice")
ExerciseAttempt = apps.get_model("activities", "ExerciseAttempt")
ExerciseAnswer = apps.get_model("activities", "ExerciseAnswer")
# content.Lesson expected in your project
Lesson = apps.get_model("content", "Lesson")
Module = apps.get_model("content", "Module")
Course = apps.get_model("content", "Course")

User = get_user_model()

BASE = "/api/activities/"



class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda o: f"{o.username}@example.com")
    is_active = True
    is_staff = False
    # default password
    @factory.post_generation
    def set_password(obj, create, extracted, **kwargs):
        raw = extracted or "password123"
        obj.set_password(raw)
        if create:
            obj.save()


class CourseFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Course

    id = factory.LazyFunction(lambda: uuid.uuid4())
    title = factory.LazyAttribute(lambda o: f"Course {uuid.uuid4().hex[:6]}")
    grade = "1"
    published = True
    owner = factory.SubFactory(UserFactory)


class ModuleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Module

    id = factory.LazyFunction(lambda: uuid.uuid4())
    course = factory.SubFactory(CourseFactory)
    title = factory.LazyAttribute(lambda o: f"Module {uuid.uuid4().hex[:6]}")
    position = 0


class LessonFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Lesson

    # Fill fields according to your Lesson model signature.
    # If Lesson requires fields, adjust here. We'll set a title if exists.
    if hasattr(Lesson, "title"):
        title = factory.LazyAttribute(lambda o: f"Lesson {uuid.uuid4().hex[:6]}")
    module = factory.SubFactory(ModuleFactory)
    position = 0
    content_type = "lesson"
    published = True


class ExerciseFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Exercise

    id = factory.LazyFunction(lambda: uuid.uuid4())
    lesson = factory.SubFactory(LessonFactory)
    title = factory.LazyAttribute(lambda o: f"Exercise {uuid.uuid4().hex[:6]}")
    # Use one of allowed type values in your model; many examples used 'mcq'
    type = "mcq"
    metadata = {}
    # settings might be stored on model.settings (JSONField) or related model
    settings = factory.LazyFunction(lambda: {})


class QuestionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Question

    id = factory.LazyFunction(lambda: uuid.uuid4())
    exercise = factory.SubFactory(ExerciseFactory)
    prompt = factory.LazyAttribute(lambda o: f"What is {uuid.uuid4().hex[:4]} ?")
    meta = factory.LazyFunction(lambda: {"type": "mcq", "points": 1})


class ChoiceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Choice

    id = factory.LazyFunction(lambda: uuid.uuid4())
    question = factory.SubFactory(QuestionFactory)
    text = factory.LazyAttribute(lambda o: f"Choice {uuid.uuid4().hex[:4]}")
    is_correct = False
    position = 0


class AttemptFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ExerciseAttempt

    id = factory.LazyFunction(lambda: uuid.uuid4())
    exercise = factory.SubFactory(ExerciseFactory)
    student = factory.SubFactory(UserFactory)
    started_at = factory.LazyFunction(timezone.now)
    status = "in_progress"
    metadata = factory.LazyFunction(lambda: {})


class AnswerFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ExerciseAnswer

    id = factory.LazyFunction(lambda: uuid.uuid4())
    attempt = factory.SubFactory(AttemptFactory)
    question = factory.SubFactory(QuestionFactory)
    answer = factory.LazyFunction(lambda: {})
    correct = False
