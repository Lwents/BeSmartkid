# content/tests/factories.py
import factory
from datetime import datetime
from django.utils import timezone
from rest_framework.authtoken.models import Token

# import project models
from custom_account.models import UserModel
from content import models as content_models

class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UserModel

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda o: f"{o.username}@example.com")
    role = "student"
    phone = factory.Faker("phone_number")
    is_active = True
    is_staff = False
    created_on = factory.LazyFunction(timezone.now)
    updated_on = factory.LazyFunction(timezone.now)

    @factory.post_generation
    def set_password(obj, create, extracted, **kwargs):
        raw = extracted or "password123"
        obj.set_password(raw)
        if create:
            obj.save()
            # ensure token exists for convenience
            Token.objects.get_or_create(user=obj)


class SubjectFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = content_models.Subject

    title = factory.Sequence(lambda n: f"Subject {n}")
    slug = factory.LazyAttribute(lambda o: o.title.lower().replace(" ", "-"))


class CourseFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = content_models.Course

    subject = factory.SubFactory(SubjectFactory)
    title = factory.Sequence(lambda n: f"Course {n}")
    description = "A sample course"
    grade = "1"
    published = False
    owner = factory.SubFactory(UserFactory)
    slug = factory.LazyAttribute(lambda o: o.title.lower().replace(" ", "-"))


class ModuleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = content_models.Module

    course = factory.SubFactory(CourseFactory)
    title = factory.Sequence(lambda n: f"Module {n}")
    position = 0


class LessonFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = content_models.Lesson

    module = factory.SubFactory(ModuleFactory)
    title = factory.Sequence(lambda n: f"Lesson {n}")
    position = 0
    content_type = "lesson"
    published = False


class LessonVersionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = content_models.LessonVersion

    lesson = factory.SubFactory(LessonFactory)
    version = 1
    status = "draft"
    author = factory.SubFactory(UserFactory)
    content = factory.LazyFunction(lambda: {"content_blocks": []})
    created_at = factory.LazyFunction(timezone.now)


class ContentBlockFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = content_models.ContentBlock

    lesson_version = factory.SubFactory(LessonVersionFactory)
    type = "text"
    position = 0
    payload = factory.LazyFunction(lambda: {"text": "Hello world"})


class ExplorationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = content_models.Exploration

    title = factory.Sequence(lambda n: f"Exploration {n}")
    owner = factory.SubFactory(UserFactory)
    language = "vi"
    published = False


class ExplorationStateFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = content_models.ExplorationState

    exploration = factory.SubFactory(ExplorationFactory)
    name = factory.Sequence(lambda n: f"state_{n}")
    content = factory.LazyFunction(lambda: {"prompt": "Hello"})
    interaction = factory.LazyFunction(lambda: {"type": "text"})

class ExplorationTransitionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = content_models.ExplorationTransition

    exploration = factory.SubFactory(ExplorationFactory)
    from_state = factory.SubFactory(ExplorationStateFactory)
    to_state = factory.SubFactory(ExplorationStateFactory)
    condition = factory.LazyFunction(lambda: {"always": True})
