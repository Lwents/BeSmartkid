import uuid
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator

# Create your models here.
class SubscriptionPlan(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    duration_days = models.IntegerField(validators=[MinValueValidator(1)])
    features = models.JSONField(default=list)  # e.g., ['unlimited_lessons', 'ai_personalization']

    class Meta:
        verbose_name = ('Subscription Plan')
        verbose_name_plural = ('Subscription Plans')

    def __str__(self):
        return self.name

class Payment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payments')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=32,
        default='pending',
        choices=[('pending', ('Pending')), ('paid', ('Paid')), ('failed', ('Failed')), ('refunded', ('Refunded'))]
    )
    paid_at = models.DateTimeField(null=True, blank=True)
    transaction_id = models.CharField(max_length=255, unique=True, blank=True, null=True)
    metadata = models.JSONField(default=dict)  # e.g., {'gateway': 'vnpay'}

    class Meta:
        verbose_name = ('Payment')
        verbose_name_plural = ('Payments')
        ordering = ['-paid_at', '-created_at']

    def __str__(self):
        return f"Payment {self.amount} by {self.user}"

class UserSubscription(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='subscriptions')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.CASCADE, related_name='user_subscriptions')
    start_date = models.DateTimeField(auto_now_add=True)
    end_date = models.DateTimeField()
    active = models.BooleanField(default=True)
    payment = models.ForeignKey(Payment, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        verbose_name = ('User Subscription')
        verbose_name_plural = ('User Subscriptions')

    def __str__(self):
        return f"{self.plan} for {self.user}"
