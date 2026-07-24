import uuid
from django.db import models
from django.db.models.signals import post_save
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.dispatch import receiver
from django.utils import timezone
from django.conf import settings



# Create your models here.
class UserManager(BaseUserManager):
    def create_user(self, username, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email must be set')
        email = self.normalize_email(email)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, username, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(username, email, password, **extra_fields)
    

class UserModel(AbstractBaseUser, PermissionsMixin):
    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(unique=True)
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)
    role = models.CharField(max_length=20, 
                            choices=[('student', 'Student'), 
                                     ('instructor', 'Instructor'), 
                                     ('admin', 'Admin')], 
                            default='student')
    phone = models.CharField(max_length=15, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    failed_login_count = models.PositiveSmallIntegerField(default=0)
    last_failed_login_at = models.DateTimeField(null=True, blank=True)
    lockout_until = models.DateTimeField(null=True, blank=True)
    lockout_strikes = models.PositiveSmallIntegerField(default=0)

    objects = UserManager()

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email']

    class Meta:
        app_label = 'custom_account'
        indexes = [models.Index(fields=['role'])]
        verbose_name = ('User')
        verbose_name_plural = ('Users')
        ordering = ['email']

    def __str__(self):
        return self.email

    def get_full_name(self):
        try:
            profile = getattr(self, 'profile', None)
            if profile and profile.display_name:
                return profile.display_name
        except Exception:
            pass
        return self.username or self.email or ''

    def get_short_name(self):
        return self.get_full_name() or self.username or self.email or ''
    

class AuthAttempt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='auth_attempts'
    )
    username_or_email = models.CharField(max_length=255, blank=True)
    success = models.BooleanField(default=False)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    error = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['created_at', 'success'])]
        ordering = ['-created_at']
        verbose_name = ('Auth Attempt')
        verbose_name_plural = ('Auth Attempts')

    def __str__(self):
        status = 'success' if self.success else 'failed'
        return f"{self.username_or_email or self.user_id} - {status}"


class SecurityPolicy(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    twofa_enforce_admin = models.BooleanField(default=False)
    twofa_enforce_teacher = models.BooleanField(default=False)
    rate_limit_login_failures = models.PositiveSmallIntegerField(default=5)
    rate_limit_window_min = models.PositiveSmallIntegerField(default=10)
    lockout_attempts = models.PositiveSmallIntegerField(default=5)
    lockout_minutes = models.PositiveSmallIntegerField(default=30)
    lockout_ban_strikes = models.PositiveSmallIntegerField(default=5)
    rbac_note = models.TextField(blank=True, default='')

    class Meta:
        verbose_name = 'Security Policy'
        verbose_name_plural = 'Security Policies'

    @classmethod
    def get_current(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Profile(models.Model):
    user = models.OneToOneField(UserModel, on_delete=models.CASCADE, primary_key=True, related_name='profile')
    display_name = models.CharField(max_length=150, blank=True, null=True)
    avatar_url = models.TextField(blank=True, null=True)
    dob = models.DateField(blank=True, null=True)
    gender = models.CharField(
        max_length=16,
        choices=[('male', ('Male')), ('female', ('Female')), ('other', ('Other'))],
        blank=True,
        null=True
    )
    language = models.CharField(max_length=20, default='vietnamese')
    metadata = models.JSONField(default=dict, blank=True)  # e.g., {'preferences': {...}}

    class Meta:
        verbose_name = ('Profile')
        verbose_name_plural = ('Profiles')

    def __str__(self):
        return f'Profile for {self.user.email}'
    

class ParentalConsent(models.Model):
    # Bổ sung: Quản lý sự đồng ý của phụ huynh cho tài khoản trẻ em (COPPA-like).
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    parent = models.ForeignKey(UserModel, on_delete=models.CASCADE, related_name='consents_given')
    child = models.ForeignKey(UserModel, on_delete=models.CASCADE, related_name='consents_received')
    consented_at = models.DateTimeField(auto_now_add=True)
    scopes = models.JSONField(default=list, blank=True)  # e.g., ['data_sharing', 'progress_view']
    revoked_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)  # e.g., {'verification_method': 'email'}

    class Meta:
        unique_together = ('parent', 'child')
        verbose_name = ('Parental Consent')
        verbose_name_plural = ('Parental Consents')
        indexes = [models.Index(fields=['parent', 'child'])]

    def __str__(self):
        return f'Consent from {self.parent} for {self.child}'


class PasswordChangeOTP(models.Model):
    user = models.ForeignKey(UserModel, on_delete=models.CASCADE, related_name='password_change_otps')
    code_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveIntegerField(default=0)
    is_used = models.BooleanField(default=False)

    class Meta:
        indexes = [models.Index(fields=['user', '-created_at'])]
        ordering = ['-created_at']

    def mark_attempt(self, save=True):
        self.attempts = models.F('attempts') + 1
        if save:
            self.save(update_fields=['attempts'])

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at


class LoginOTP(models.Model):
    user = models.ForeignKey(UserModel, on_delete=models.CASCADE, related_name='login_otps')
    code_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveIntegerField(default=0)
    is_used = models.BooleanField(default=False)

    class Meta:
        indexes = [models.Index(fields=['user', '-created_at'])]
        ordering = ['-created_at']

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at
