import base64
import json
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Count, Sum, Q
from django.urls import reverse
from django.utils import timezone
from django.conf import settings
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404

from payments.api.serializers import (
    MomoPaymentInitSerializer,
    SubscriptionPlanSerializer,
    PaymentHistorySerializer,
)
from payments.models import Payment, UserSubscription, SubscriptionPlan
from payments.services.momo_client import MoMoAIOClient


def _enroll_paid_courses(payment):
    """Activate every course attached to a successful payment on the server."""
    from content.models import Course, Enrollment

    metadata = payment.metadata if isinstance(payment.metadata, dict) else {}
    raw_ids = metadata.get("course_ids") or []
    course_ids = [str(value).strip() for value in raw_ids if str(value).strip()]
    if not course_ids:
        return
    for course in Course.objects.filter(id__in=course_ids, published=True):
        Enrollment.objects.get_or_create(student=payment.user, course=course)


class MoMoPaymentInitView(APIView):
    """Khởi tạo giao dịch MoMo từ FE."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = MomoPaymentInitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        plan = serializer.validated_data["plan"]
        amount = serializer.validated_data["amount"]
        description = serializer.validated_data["description"]
        course_ids = serializer.validated_data.get("course_ids") or []
        course_titles = serializer.validated_data.get("course_titles") or []
        flow = request.data.get("flow", "pay_with_method")
        payment_code = request.data.get("payment_code", "")

        payment = Payment.objects.create(
            user=request.user,
            plan=plan,
            amount=amount,
            status="pending",
            metadata={
                "gateway": "momo",
                "flow": flow,
                "title": description,
                "course_ids": course_ids,
                "course_titles": course_titles,
            },
        )

        order_id = payment.id.hex
        extra_payload = {
            "payment_id": str(payment.id),
            "user_id": str(request.user.id),
        }
        if plan:
            extra_payload["plan_id"] = str(plan.id)
        extra_data = base64.b64encode(json.dumps(extra_payload).encode("utf-8")).decode("utf-8")

        amount_vnd = int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        # Prefer FE-provided redirect_url if validated, else fallback to settings
        redirect_url = (
            serializer.validated_data.get("redirect_url")
            or getattr(settings, "MOMO_REDIRECT_URL", None)
            or request.build_absolute_uri("/")
        )
        ipn_url = getattr(settings, "MOMO_IPN_URL", None) or request.build_absolute_uri(reverse("payments:momo-ipn"))

        try:
            client = MoMoAIOClient()
        except ValueError as config_error:
            payment.status = "failed"
            payment.metadata = {**payment.metadata, "error": str(config_error)}
            payment.save(update_fields=["status", "metadata"])
            return Response(
                {
                    "detail": "MoMo payment gateway is not properly configured. Please contact administrator.",
                    "error": str(config_error),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        try:
            if flow == "pay_with_method":
                momo_response = client.create_pay_with_method(
                    amount=amount_vnd,
                    order_id=order_id,
                    order_info=description,
                    redirect_url=redirect_url,
                    ipn_url=ipn_url,
                    extra_data=extra_data,
                )
            elif flow == "pos":
                momo_response = client.create_pos_payment(
                    amount=amount_vnd,
                    order_id=order_id,
                    order_info=description,
                    payment_code=payment_code,
                    ipn_url=ipn_url,
                    extra_data=extra_data,
                )
            else:
                momo_response = client.create_payment(
                    amount=amount_vnd,
                    order_id=order_id,
                    order_info=description,
                    redirect_url=redirect_url,
                    ipn_url=ipn_url,
                    extra_data=extra_data,
                )
        except ValueError as exc:
            payment.status = "failed"
            payment.metadata["error"] = str(exc)
            payment.save(update_fields=["status", "metadata"])
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        updated_metadata = {
            **payment.metadata,
            "orderId": momo_response.get("orderId"),
            "requestId": momo_response.get("requestId"),
            "payUrl": momo_response.get("payUrl"),
        }
        payment.metadata = updated_metadata
        payment.save(update_fields=["metadata"])

        return Response(
            {
                "payment_id": str(payment.id),
                "payUrl": momo_response.get("payUrl"),
                "deeplink": momo_response.get("deeplink"),
                "qrCodeUrl": momo_response.get("qrCodeUrl"),
                "resultCode": momo_response.get("resultCode"),
                "message": momo_response.get("message"),
            }
        )


class MoMoIPNView(APIView):
    """Endpoint nhận thông báo thanh toán từ MoMo."""

    authentication_classes: list = []
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        data = request.data
        try:
            client = MoMoAIOClient()
        except ValueError as config_error:
            return Response(
                {"message": "MoMo gateway not configured", "error": str(config_error)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if not client.verify_ipn(data):
            return Response({"message": "invalid signature"}, status=status.HTTP_400_BAD_REQUEST)

        order_id = data.get("orderId")
        if not order_id:
            return Response({"message": "orderId missing"}, status=status.HTTP_400_BAD_REQUEST)

        payment = Payment.objects.filter(metadata__orderId=order_id).first()
        if not payment:
            return Response({"message": "payment not found"}, status=status.HTTP_404_NOT_FOUND)

        payment.metadata = {**payment.metadata, "momo_ipn": data}
        result_code = data.get("resultCode")

        if result_code == 0:
            with transaction.atomic():
                payment.status = "paid"
                payment.transaction_id = data.get("transId")
                payment.paid_at = payment.paid_at or timezone.now()
                payment.save(update_fields=["status", "transaction_id", "paid_at", "metadata"])
                _enroll_paid_courses(payment)

                if payment.plan:
                    subscription, created = UserSubscription.objects.get_or_create(
                        user=payment.user,
                        plan=payment.plan,
                        defaults={
                            "start_date": timezone.now(),
                            "end_date": timezone.now() + timedelta(days=payment.plan.duration_days),
                            "active": True,
                            "payment": payment,
                        },
                    )
                    if not created:
                        base_date = max(subscription.end_date, timezone.now())
                        subscription.end_date = base_date + timedelta(days=payment.plan.duration_days)
                        subscription.active = True
                        subscription.payment = payment
                        subscription.save(update_fields=["end_date", "active", "payment"])
        else:
            payment.status = "failed"
            payment.save(update_fields=["status", "metadata"])

        return Response({"message": "success"}, status=status.HTTP_200_OK)


class SubscriptionPlanListView(generics.ListAPIView):
    """
    Public endpoint to expose active subscription plans for the frontend.
    """

    queryset = SubscriptionPlan.objects.all().order_by("price")
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [permissions.AllowAny]


class PaymentHistoryListView(generics.ListAPIView):
    """Lịch sử thanh toán của chính người dùng (có phân trang)."""

    serializer_class = PaymentHistorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Payment.objects.filter(user=self.request.user).order_by("-paid_at", "-created_at")
        status_param = self.request.query_params.get("status")
        if status_param in {"pending", "paid", "failed", "refunded"}:
            qs = qs.filter(status=status_param)
        gateway = self.request.query_params.get("gateway")
        if gateway:
            qs = qs.filter(metadata__gateway__iexact=gateway)
        return qs

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)

        summary_qs = self.filter_queryset(self.get_queryset())
        aggregates = summary_qs.aggregate(
            total_amount_paid=Sum("amount", filter=Q(status__in=["paid", "refunded"])),
            total_success=Count("id", filter=Q(status__in=["paid", "refunded"])),
            total_pending=Count("id", filter=Q(status="pending")),
            total_failed=Count("id", filter=Q(status="failed")),
        )
        summary = {
            "total_amount": float(aggregates.get("total_amount_paid") or 0),
            "success_count": aggregates.get("total_success") or 0,
            "pending_count": aggregates.get("total_pending") or 0,
            "failed_count": aggregates.get("total_failed") or 0,
        }

        if isinstance(response.data, dict):
            response.data["summary"] = summary
        else:
            response.data = {"results": response.data, "summary": summary}
        return response


class MoMoSyncPaymentView(APIView):
    """Manual sync with MoMo to update a payment status by payment id.

    Useful in development when IPN cannot reach local backend.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        payment = get_object_or_404(Payment, id=pk, user=request.user)
        order_id = (payment.metadata or {}).get("orderId") or payment.id.hex
        request_id = (payment.metadata or {}).get("requestId")

        try:
            client = MoMoAIOClient()
        except ValueError as config_error:
            return Response(
                {"detail": "MoMo gateway not configured", "error": str(config_error)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        try:
            momo_res = client.query_status(order_id=order_id, request_id=request_id)
        except ValueError as exc:
            payment.status = "failed"
            payment.metadata = {
                **(payment.metadata or {}),
                "momo_sync_error": str(exc),
            }
            payment.save(update_fields=["status", "metadata"])
            return Response({"detail": str(exc), "status": payment.status}, status=status.HTTP_400_BAD_REQUEST)

        payment.metadata = {**(payment.metadata or {}), "momo_query": momo_res}
        result_code = momo_res.get("resultCode")
        trans_id = momo_res.get("transId") or momo_res.get("transactionId")

        if result_code == 0:
            # success
            if payment.status != "paid":
                with transaction.atomic():
                    payment.status = "paid"
                    if trans_id and not payment.transaction_id:
                        payment.transaction_id = str(trans_id)
                    if not payment.paid_at:
                        payment.paid_at = timezone.now()
                    payment.save(update_fields=["status", "transaction_id", "paid_at", "metadata"])
                    _enroll_paid_courses(payment)

                    # Tạo/cập nhật subscription nếu có plan (giống MoMoIPNView)
                    if payment.plan:
                        subscription, created = UserSubscription.objects.get_or_create(
                            user=payment.user,
                            plan=payment.plan,
                            defaults={
                                "start_date": timezone.now(),
                                "end_date": timezone.now() + timedelta(days=payment.plan.duration_days),
                                "active": True,
                                "payment": payment,
                            },
                        )
                        if not created:
                            base_date = max(subscription.end_date, timezone.now())
                            subscription.end_date = base_date + timedelta(days=payment.plan.duration_days)
                            subscription.active = True
                            subscription.payment = payment
                            subscription.save(update_fields=["end_date", "active", "payment"])
        elif result_code in {1000, 7000}:
            # 1000: transaction not found or still pending in some docs; keep pending
            if payment.status != "pending":
                payment.status = "pending"
                payment.save(update_fields=["status", "metadata"])
        else:
            if payment.status != "failed":
                payment.status = "failed"
                payment.save(update_fields=["status", "metadata"])

        return Response({
            "payment_id": str(payment.id),
            "status": payment.status,
            "transaction_id": payment.transaction_id,
            "resultCode": result_code,
        })
