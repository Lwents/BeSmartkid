from datetime import datetime
from uuid import UUID

from django.db.models import Q
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_api.models import AdminAuditLog
from admin_api.permissions import IsAdmin
from custom_account.models import AuthAttempt


class AdminActivityLogView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request, log_id=None):
        if log_id:
            return self.get_detail(log_id)
        return self.get_list(request)

    def get_list(self, request):
        query = (request.query_params.get('q') or '').strip()
        action_filter = (request.query_params.get('action') or '').strip()
        user_id = (request.query_params.get('userId') or '').strip()
        from_date = self._parse_date(request.query_params.get('from'))
        to_date = self._parse_date(request.query_params.get('to'))
        page = self._positive_int(request.query_params.get('page'), 1)
        page_size = min(self._positive_int(request.query_params.get('pageSize'), 20), 100)

        audit_qs = AdminAuditLog.objects.select_related('actor')
        auth_qs = AuthAttempt.objects.select_related('user')
        if query:
            audit_qs = audit_qs.filter(
                Q(action__icontains=query)
                | Q(actor__email__icontains=query)
                | Q(actor__username__icontains=query)
            )
            auth_qs = auth_qs.filter(
                Q(username_or_email__icontains=query)
                | Q(user__email__icontains=query)
            )
        if action_filter:
            audit_qs = audit_qs.filter(action__icontains=action_filter)
            if 'login' not in action_filter:
                auth_qs = auth_qs.none()
        if user_id:
            audit_qs = audit_qs.filter(actor_id=user_id)
            auth_qs = auth_qs.filter(user_id=user_id)
        if from_date:
            audit_qs = audit_qs.filter(created_at__gte=from_date)
            auth_qs = auth_qs.filter(created_at__gte=from_date)
        if to_date:
            audit_qs = audit_qs.filter(created_at__lte=to_date)
            auth_qs = auth_qs.filter(created_at__lte=to_date)

        items = [self._audit_item(item) for item in audit_qs[:500]]
        items.extend(self._auth_item(item) for item in auth_qs[:500])
        items.sort(key=lambda item: item['timestamp'], reverse=True)
        total = len(items)
        start = (page - 1) * page_size
        return Response({
            'items': items[start:start + page_size],
            'total': total,
            'page': page,
            'pageSize': page_size,
        }, status=status.HTTP_200_OK)

    def get_detail(self, log_id):
        object_id = self._parse_uuid(log_id.split(':', 1)[1]) if ':' in log_id else None
        if log_id.startswith('audit:'):
            item = (
                AdminAuditLog.objects.select_related('actor').filter(pk=object_id).first()
                if object_id else None
            )
            payload = self._audit_item(item) if item else None
        elif log_id.startswith('auth:'):
            item = (
                AuthAttempt.objects.select_related('user').filter(pk=object_id).first()
                if object_id else None
            )
            payload = self._auth_item(item) if item else None
        else:
            payload = None
        if not payload:
            return Response(
                {'detail': 'Không tìm thấy nhật ký hoạt động.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(payload, status=status.HTTP_200_OK)

    def _audit_item(self, item):
        if not item:
            return None
        return {
            'id': f'audit:{item.id}',
            'userId': str(item.actor_id or ''),
            'userEmail': item.actor.email if item.actor else 'Hệ thống',
            'action': item.action,
            'timestamp': item.created_at.isoformat(),
            'status': item.status,
            'ip': item.ip_address,
            'userAgent': item.user_agent,
            'details': item.details,
        }

    def _auth_item(self, item):
        return {
            'id': f'auth:{item.id}',
            'userId': str(item.user_id or ''),
            'userEmail': item.user.email if item.user else item.username_or_email,
            'action': 'user.login' if item.success else 'user.login_failed',
            'timestamp': item.created_at.isoformat(),
            'status': 'success' if item.success else 'failed',
            'ip': item.ip_address,
            'userAgent': item.user_agent,
            'details': {'error': item.error} if item.error else {},
        }

    def _parse_date(self, value):
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        except (TypeError, ValueError):
            return None

    def _positive_int(self, value, default):
        try:
            return max(1, int(value))
        except (TypeError, ValueError):
            return default

    def _parse_uuid(self, value):
        try:
            return UUID(str(value))
        except (TypeError, ValueError, AttributeError):
            return None
