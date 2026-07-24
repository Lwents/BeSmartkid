from decimal import Decimal

from rest_framework import serializers
from django.conf import settings

from payments.models import SubscriptionPlan, Payment


class MomoPaymentInitSerializer(serializers.Serializer):
    plan_id = serializers.UUIDField(required=False)
    amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.01"),
        required=False,
    )
    description = serializers.CharField(max_length=255, required=False, allow_blank=True)
    redirect_url = serializers.URLField(required=False)
    course_ids = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
    )
    course_titles = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
    )

    def validate(self, attrs):
        plan_id = attrs.get("plan_id")
        amount = attrs.get("amount")
        course_ids = attrs.get("course_ids") or []
        course_titles = attrs.get("course_titles") or []
        if not plan_id and amount is None:
            raise serializers.ValidationError("Either plan_id or amount is required.")
        if plan_id and amount is not None:
            raise serializers.ValidationError("Provide either plan_id or amount, not both.")
        attrs["course_ids"] = course_ids
        attrs["course_titles"] = course_titles

        if plan_id:
            try:
                plan = SubscriptionPlan.objects.get(id=plan_id)
            except SubscriptionPlan.DoesNotExist as exc:
                raise serializers.ValidationError({"plan_id": "Subscription plan not found."}) from exc
            attrs["plan"] = plan
            attrs["amount"] = plan.price
            if not attrs.get("description"):
                attrs["description"] = f"Thanh toán gói {plan.name}"
        else:
            attrs["plan"] = None
            if not attrs.get("description"):
                attrs["description"] = "Thanh toán MoMo"
            min_amount = getattr(settings, "MOMO_MIN_CUSTOM_AMOUNT", Decimal("1000"))
            if amount is None:
                raise serializers.ValidationError({"amount": "Số tiền thanh toán là bắt buộc."})
            if amount < min_amount:
                human_min = f"{int(min_amount):,}".replace(",", ".")
                raise serializers.ValidationError({
                    "amount": f"Số tiền tối thiểu cho thanh toán MoMo tuỳ chỉnh là {human_min} ₫."
                })

        # Optional redirect_url with basic whitelist to avoid open redirect
        redirect = attrs.get("redirect_url")
        if redirect:
            allowed_prefixes = [
                getattr(settings, "FRONTEND_URL", "").rstrip("/"),
            ]
            # Add common local dev origins
            allowed_prefixes += [
                "http://127.0.0.1:5173",
                "http://localhost:5173",
            ]
            # Add CORS_ALLOWED_ORIGINS if any
            try:
                from urllib.parse import urlparse
                cors = getattr(settings, "CORS_ALLOWED_ORIGINS", []) or []
                allowed_prefixes += [u.rstrip("/") for u in cors]
            except Exception:
                pass

            redirect_ok = any(redirect.startswith(p) and p for p in allowed_prefixes)
            if not redirect_ok:
                raise serializers.ValidationError({
                    "redirect_url": "Redirect URL is not allowed."
                })

        return attrs


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = ("id", "name", "price", "duration_days", "features")


class PaymentHistorySerializer(serializers.ModelSerializer):
    plan_name = serializers.SerializerMethodField()
    gateway = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = (
            "id",
            "amount",
            "status",
            "created_at",
            "paid_at",
            "transaction_id",
            "plan",  # UUID
            "plan_name",
            "gateway",
            "metadata",
        )

    def get_plan_name(self, obj: Payment) -> str:
        if obj.plan:
            return obj.plan.name
        meta = obj.metadata or {}
        titles = meta.get("course_titles") or meta.get("title")
        if isinstance(titles, list) and titles:
            return titles[0]
        if isinstance(titles, str) and titles:
            return titles
        return "Thanh toán tuỳ chỉnh"

    def get_gateway(self, obj: Payment) -> str:
        return (obj.metadata or {}).get("gateway") or "momo"
