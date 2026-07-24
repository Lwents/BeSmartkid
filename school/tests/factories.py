# school/tests/factories.py
import factory
from django.utils import timezone
from school.models import SchoolModel, ClassroomModel, Enrollment

class SchoolFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SchoolModel

    name = factory.Sequence(lambda n: f"School {n}")
    address = factory.Faker("address")
    phone = factory.Faker("phone_number")
    created_on = factory.LazyFunction(timezone.now)

class ClassroomFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ClassroomModel

    school = factory.SubFactory(SchoolFactory)
    name = factory.Sequence(lambda n: f"Class {n}")
    grade = factory.Iterator(["1", "2", "3", "4", "5"])
    metadata = {}

class EnrollmentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Enrollment

    student = factory.SubFactory("account.tests.factories.UserFactory", role="student")
    classroom = factory.SubFactory(ClassroomFactory)
    joined_on = factory.LazyFunction(timezone.now)
    is_active = True


class TeacherAssignmentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "school.TeacherAssignment"

    teacher = factory.SubFactory("account.tests.factories.UserFactory", role="instructor")
    classroom = factory.SubFactory(ClassroomFactory)
    assigned_on = factory.LazyFunction(timezone.now)
    is_active = True


class SchoolYearFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "school.SchoolYear"

    name = factory.Sequence(lambda n: f"School Year {n}")
    start_date = factory.LazyFunction(timezone.now)
    end_date = factory.LazyFunction(lambda: timezone.now() + timezone.timedelta(days=365))
    is_active = True
