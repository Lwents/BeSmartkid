from datetime import datetime, timedelta
from django.db.models import Q, Sum, Count
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.utils import timezone
import csv
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from admin_api.permissions import IsAdmin
from payments.models import Payment


class AdminTransactionListView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        """List all transactions with filtering and pagination"""
        q = request.query_params.get('q', '')
        status_filter = request.query_params.get('status')
        gateway = request.query_params.get('gateway')
        user_id = request.query_params.get('userId')
        course_id = request.query_params.get('courseId')
        from_date = request.query_params.get('from')
        to_date = request.query_params.get('to')
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('pageSize', 20))

        queryset = Payment.objects.select_related('user', 'plan')

        # Apply filters
        if q:
            queryset = queryset.filter(
                Q(id__icontains=q) |
                Q(user__email__icontains=q) |
                Q(transaction_id__icontains=q)
            )

        if status_filter:
            queryset = queryset.filter(status=status_filter.lower())

        if gateway:
            # Case-insensitive gateway filter
            queryset = queryset.filter(metadata__gateway__iexact=gateway)

        if user_id:
            queryset = queryset.filter(user_id=user_id)

        if from_date:
            queryset = queryset.filter(created_at__gte=from_date)

        if to_date:
            queryset = queryset.filter(created_at__lte=to_date)

        # Paginate
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)

        # Serialize
        items = []
        for tx in page_obj:
            gateway_name = tx.metadata.get('gateway', 'N/A') if tx.metadata else 'N/A'
            meta = tx.metadata or {}
            course_ids = meta.get('course_ids') or []
            course_titles = meta.get('course_titles') or []
            if isinstance(course_titles, str):
                course_titles = [course_titles]
            course_id = str(tx.plan.id) if tx.plan else (str(course_ids[0]) if course_ids else None)
            course_title = tx.plan.name if tx.plan else (
                course_titles[0] if course_titles else meta.get('title') or 'N/A'
            )
            items.append({
                'id': str(tx.id),
                'userId': str(tx.user.id) if tx.user else None,
                'buyerName': tx.user.email if tx.user else 'N/A',
                'buyerEmail': tx.user.email if tx.user else 'N/A',
                'courseId': course_id,
                'courseTitle': course_title,
                'amount': float(tx.amount),
                'currency': 'VND',
                'gateway': gateway_name,
                'status': tx.status.capitalize(),
                'createdAt': tx.created_at.isoformat() if tx.created_at else None,
                'settledAt': tx.paid_at.isoformat() if tx.paid_at else None
            })

        return Response({
            'items': items,
            'total': paginator.count
        }, status=status.HTTP_200_OK)


class AdminTransactionDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request, pk):
        """Get transaction detail"""
        try:
            tx = Payment.objects.select_related('user', 'plan').get(id=pk)
        except Payment.DoesNotExist:
            return Response({'error': 'Transaction not found'}, status=status.HTTP_404_NOT_FOUND)

        gateway_name = tx.metadata.get('gateway', 'N/A') if tx.metadata else 'N/A'
        # Gateway fee chưa được lưu trong Payment; trả 0 thay vì bịa tỷ lệ 3%.
        fees = 0.0
        net = float(tx.amount) if tx.status == 'paid' else 0.0

        meta = tx.metadata or {}
        course_ids = meta.get('course_ids') or []
        course_titles = meta.get('course_titles') or []
        if isinstance(course_titles, str):
            course_titles = [course_titles]
        course_id = str(tx.plan.id) if tx.plan else (str(course_ids[0]) if course_ids else None)
        course_title = tx.plan.name if tx.plan else (
            course_titles[0] if course_titles else meta.get('title') or 'N/A'
        )

        # Build events (mock - need actual event log)
        events = [
            {
                'time': tx.created_at.isoformat() if tx.created_at else None,
                'type': 'created',
                'description': 'Tạo giao dịch'
            }
        ]
        if tx.paid_at:
            events.append({
                'time': tx.paid_at.isoformat(),
                'type': 'succeeded' if tx.status == 'paid' else 'failed',
                'description': 'Thanh toán thành công' if tx.status == 'paid' else 'Thanh toán thất bại'
            })
        if tx.status == 'refunded':
            events.append({
                'time': tx.paid_at.isoformat() if tx.paid_at else None,
                'type': 'refunded',
                'description': 'Hoàn tiền'
            })

        return Response({
            'id': str(tx.id),
            'userId': str(tx.user.id) if tx.user else None,
            'buyerName': tx.user.email if tx.user else 'N/A',
            'buyerEmail': tx.user.email if tx.user else 'N/A',
            'courseId': course_id,
            'courseTitle': course_title,
            'amount': float(tx.amount),
            'currency': 'VND',
            'gateway': gateway_name,
            'status': tx.status.capitalize(),
            'createdAt': tx.created_at.isoformat() if tx.created_at else None,
            'settledAt': tx.paid_at.isoformat() if tx.paid_at else None,
            'fees': fees,
            'net': net,
            'reference': tx.transaction_id or None,
            'events': events,
            'tags': []
        }, status=status.HTTP_200_OK)


class AdminTransactionMetricsView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        """Get transaction metrics"""
        from_date = request.query_params.get('from')
        to_date = request.query_params.get('to')

        queryset = Payment.objects.all()

        if from_date:
            queryset = queryset.filter(created_at__gte=from_date)
        if to_date:
            queryset = queryset.filter(created_at__lte=to_date)

        total_amount = queryset.filter(status__in=['paid', 'refunded']).aggregate(total=Sum('amount'))['total'] or 0
        count = queryset.count()
        refunds_queryset = queryset.filter(status='refunded')
        refunds = refunds_queryset.aggregate(total=Sum('amount'))['total'] or 0
        net = float(total_amount) - float(refunds)
        disputed = queryset.filter(metadata__disputed=True).count()

        return Response({
            'count': count,
            'gross': float(total_amount),
            'net': float(net),
            'refunds': float(refunds),
            'disputed': disputed
        }, status=status.HTTP_200_OK)


class AdminTransactionRefundView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, pk):
        """Refund a transaction"""
        try:
            tx = Payment.objects.get(id=pk)
        except Payment.DoesNotExist:
            return Response({'error': 'Transaction not found'}, status=status.HTTP_404_NOT_FOUND)

        amount = request.data.get('amount')
        reason = request.data.get('reason', '')

        if tx.status != 'paid':
            return Response({'error': 'Can only refund paid transactions'}, status=status.HTTP_400_BAD_REQUEST)

        # Update status
        tx.status = 'refunded'
        tx.save()

        return Response({'success': True}, status=status.HTTP_200_OK)


class AdminTransactionDisputeView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, pk):
        """Mark transaction as disputed"""
        try:
            tx = Payment.objects.get(id=pk)
        except Payment.DoesNotExist:
            return Response({'error': 'Transaction not found'}, status=status.HTTP_404_NOT_FOUND)

        note = request.data.get('note', '')

        # Could add a dispute field or status
        # For now, just update metadata
        if not tx.metadata:
            tx.metadata = {}
        tx.metadata['disputed'] = True
        tx.metadata['dispute_note'] = note
        tx.save()

        return Response({'success': True}, status=status.HTTP_200_OK)


class AdminTransactionExportView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        """Export transactions as CSV"""
        # Get same filters as list
        q = request.query_params.get('q', '')
        status_filter = request.query_params.get('status')
        gateway = request.query_params.get('gateway')
        from_date = request.query_params.get('from')
        to_date = request.query_params.get('to')

        queryset = Payment.objects.select_related('user', 'plan')

        if q:
            queryset = queryset.filter(
                Q(id__icontains=q) |
                Q(user__email__icontains=q)
            )
        if status_filter:
            queryset = queryset.filter(status=status_filter.lower())
        if gateway:
            queryset = queryset.filter(metadata__gateway__iexact=gateway)
        if from_date:
            queryset = queryset.filter(created_at__gte=from_date)
        if to_date:
            queryset = queryset.filter(created_at__lte=to_date)

        # Create CSV
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="transactions.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'id', 'buyerName', 'buyerEmail', 'courseTitle', 'amount',
            'currency', 'gateway', 'status', 'createdAt', 'settledAt'
        ])

        for tx in queryset:
            gateway_name = tx.metadata.get('gateway', 'N/A') if tx.metadata else 'N/A'
            writer.writerow([
                str(tx.id),
                tx.user.email if tx.user else 'N/A',
                tx.user.email if tx.user else 'N/A',
                tx.plan.name if tx.plan else 'N/A',
                float(tx.amount),
                'VND',
                gateway_name,
                tx.status,
                tx.created_at.isoformat() if tx.created_at else '',
                tx.paid_at.isoformat() if tx.paid_at else ''
            ])

        return response

