from django.urls import path

from payments.api.views import (
    MoMoPaymentInitView,
    MoMoIPNView,
    SubscriptionPlanListView,
    PaymentHistoryListView,
    MoMoSyncPaymentView,
)

app_name = "payments"

urlpatterns = [
    path("plans/", SubscriptionPlanListView.as_view(), name="plan-list"),
    path("history/", PaymentHistoryListView.as_view(), name="payment-history"),
    path("momo/initiate/", MoMoPaymentInitView.as_view(), name="momo-init"),
    path("momo/ipn/", MoMoIPNView.as_view(), name="momo-ipn"),
    path("momo/sync/<uuid:pk>/", MoMoSyncPaymentView.as_view(), name="momo-sync"),
]
