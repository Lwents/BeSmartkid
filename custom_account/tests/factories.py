# from factories import factory
# from django.contrib.auth import get_user_model

# User = get_user_model()

# class UserFactory(factory.django.DjangoModelFactory):
#     class Meta:
#         model = User

#     username = factory.Sequence(lambda n: f"user{n}")
#     email = factory.LazyAttribute(lambda obj: f"{obj.username}@example.com")
#     password = factory.PostGenerationMethodCall("set_password", "Secure123")
#     first_name = "Test"
#     last_name = "User"
#     role = "student"


# account/tests/factories.py
import factory
import random
from datetime import date
from faker import Faker
from django.utils import timezone

from custom_account.models import UserModel, Profile, ParentalConsent



class VietnamPhoneProvider:
    def __init__(self, generator):
        self.generator = generator  # Store the Faker generator instance

    def vietnam_mobile_number(self):
        fake = Faker()
        prefixes = [
            '032', '033', '034', '035', '036', '037', '038', '039',
            '070', '079', '077', '076', '078',
            '083', '084', '085', '081', '082',
            '088', '091', '094', '096', '097', '098', '099'
        ]
        prefix = random.choice(prefixes)
        suffix = fake.numerify(text='#######')
        return f'{prefix}{suffix}'
factory.Faker.add_provider(VietnamPhoneProvider)


class UserFactory(factory.django.DjangoModelFactory):
    """Factory for UserModel."""
    class Meta:
        model = UserModel
        skip_postgeneration_save = True

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda o: f"{o.username}@example.com")
    role = "student"
    # phone = factory.Faker('vietnam_mobile_number')
    phone = factory.LazyAttribute(lambda o: ''.join(filter(str.isdigit, factory.Faker('phone_number', locale='vi_VN').evaluate(None, None, {'locale': 'vi_VN'})))[:10])
    is_active = True
    is_staff = False
    created_on = factory.LazyFunction(timezone.now)
    updated_on = factory.LazyFunction(timezone.now)

    @factory.post_generation
    def set_password(obj, create, extracted, **kwargs):
        """
        Usage:
            UserFactory(password="plain123")
        By default uses "password123" if not provided.
        """
        raw = extracted or "password123"
        # Must call set_password and save
        obj.set_password(raw)
        if create:
            obj.save()


class ProfileFactory(factory.django.DjangoModelFactory):
    """Factory for Profile."""
    class Meta:
        model = Profile

    user = factory.SubFactory(UserFactory)
    display_name = factory.LazyAttribute(lambda o: f"DN_{o.user.username}")
    avatar_url = ""
    dob = factory.LazyFunction(lambda: date(2015, 1, 1))
    gender = "other"
    language = "vi"
    metadata = {}


class ParentalConsentFactory(factory.django.DjangoModelFactory):
    """Factory for ParentalConsent."""
    class Meta:
        model = ParentalConsent

    parent = factory.SubFactory(UserFactory, role="parent")
    child = factory.SubFactory(UserFactory, role="student")
    scopes = ["data_sharing"]
    metadata = {}
