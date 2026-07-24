from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from student_api.permissions import IsStudent
from payments.models import Payment, SubscriptionPlan
from payments.api.views import MoMoPaymentInitView


class StudentPaymentsHistoryView(APIView):
    """
    GET /api/student/payments/history/
    Returns payment history for student
    """
    permission_classes = [IsAuthenticated, IsStudent]

    def get(self, request):
        """Get student payment history"""
        student = request.user
        
        # Get query parameters
        status_filter = request.query_params.get('status', '').strip()
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('pageSize', 20))
        
        # Get payments for student - newest first
        payments = Payment.objects.filter(user=student).order_by('-created_at')
        
        # Apply status filter
        if status_filter:
            payments = payments.filter(status=status_filter)
        
        # Pagination
        total = payments.count()
        start = (page - 1) * page_size
        end = start + page_size
        payments = payments[start:end]
        
        # Calculate summary
        all_payments = Payment.objects.filter(user=student)
        summary = {
            'totalAmount': float(sum(p.amount for p in all_payments.filter(status='paid'))),
            'successCount': all_payments.filter(status='paid').count(),
            'pendingCount': all_payments.filter(status='pending').count(),
            'failedCount': all_payments.filter(status='failed').count(),
        }
        
        # Format payments
        items = []
        for payment in payments:
            plan_name = payment.plan.name if payment.plan else 'Thanh toán tuỳ chỉnh'
            gateway = payment.metadata.get('gateway', 'Momo') if payment.metadata else 'Momo'
            
            items.append({
                'id': str(payment.id),
                'orderId': payment.transaction_id or str(payment.id),
                'plan': plan_name,
                'amount': float(payment.amount),
                'method': gateway.capitalize(),
                'date': payment.paid_at.isoformat() if payment.paid_at else payment.created_at.isoformat(),
                'status': 'success' if payment.status == 'paid' else payment.status,
            })
        
        return Response({
            'items': items,
            'total': total,
            'summary': summary,
        }, status=status.HTTP_200_OK)


class StudentPaymentsInitiateView(MoMoPaymentInitView):
    """
    POST /api/student/payments/initiate/
    Initiates payment for student
    Wraps MoMoPaymentInitView with student permission check
    """
    permission_classes = [IsAuthenticated, IsStudent]

