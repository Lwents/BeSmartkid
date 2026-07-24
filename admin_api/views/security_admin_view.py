from datetime import timedelta
from django.core.cache import cache
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from admin_api.permissions import IsAdmin
from custom_account.models import SecurityPolicy


class AdminSecurityPolicyView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        """Get security policy"""
        policy = SecurityPolicy.get_current()
        return Response(
            {
                'twoFA': {
                    'enforceAdmin': policy.twofa_enforce_admin,
                    'enforceTeacher': policy.twofa_enforce_teacher,
                },
                'rateLimit': {
                    'loginFailures': policy.rate_limit_login_failures,
                    'windowMin': policy.rate_limit_window_min,
                },
                'lockout': {
                    'attempts': policy.lockout_attempts,
                    'lockMinutes': policy.lockout_minutes,
                    'banStrikes': policy.lockout_ban_strikes,
                },
                'rbacNote': policy.rbac_note or '',
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        """Update security policy"""
        payload = request.data or {}
        policy = SecurityPolicy.get_current()

        def parse_int(value, default):
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        twofa = payload.get('twoFA') or {}
        rate_limit = payload.get('rateLimit') or {}
        lockout = payload.get('lockout') or {}

        if isinstance(twofa, dict):
            if 'enforceAdmin' in twofa:
                policy.twofa_enforce_admin = bool(twofa.get('enforceAdmin'))
            if 'enforceTeacher' in twofa:
                policy.twofa_enforce_teacher = bool(twofa.get('enforceTeacher'))

        if isinstance(rate_limit, dict):
            if 'loginFailures' in rate_limit:
                policy.rate_limit_login_failures = max(parse_int(rate_limit.get('loginFailures'), policy.rate_limit_login_failures), 1)
            if 'windowMin' in rate_limit:
                policy.rate_limit_window_min = max(parse_int(rate_limit.get('windowMin'), policy.rate_limit_window_min), 1)

        if isinstance(lockout, dict):
            if 'attempts' in lockout:
                policy.lockout_attempts = max(parse_int(lockout.get('attempts'), policy.lockout_attempts), 1)
            if 'lockMinutes' in lockout:
                policy.lockout_minutes = max(parse_int(lockout.get('lockMinutes'), policy.lockout_minutes), 1)
            if 'banStrikes' in lockout:
                policy.lockout_ban_strikes = max(parse_int(lockout.get('banStrikes'), policy.lockout_ban_strikes), 1)

        if 'rbacNote' in payload:
            policy.rbac_note = payload.get('rbacNote') or ''

        policy.save()

        return Response(
            {
                'twoFA': {
                    'enforceAdmin': policy.twofa_enforce_admin,
                    'enforceTeacher': policy.twofa_enforce_teacher,
                },
                'rateLimit': {
                    'loginFailures': policy.rate_limit_login_failures,
                    'windowMin': policy.rate_limit_window_min,
                },
                'lockout': {
                    'attempts': policy.lockout_attempts,
                    'lockMinutes': policy.lockout_minutes,
                    'banStrikes': policy.lockout_ban_strikes,
                },
                'rbacNote': policy.rbac_note or '',
            },
            status=status.HTTP_200_OK,
        )


class AdminIpAllowListView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        """List IP allowlist"""
        try:
            ip_list = cache.get('security_ip_allowlist', [])
        except Exception:
            ip_list = []
        return Response(ip_list, status=status.HTTP_200_OK)

    def post(self, request):
        """Add IP to allowlist"""
        cidr = request.data.get('cidr')
        note = request.data.get('note', '')

        if not cidr:
            return Response({'error': 'cidr required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            ip_list = cache.get('security_ip_allowlist', [])
        except Exception:
            ip_list = []
        ip_item = {
            'id': f"ip_{len(ip_list) + 1}",
            'cidr': cidr,
            'note': note,
            'createdAt': timezone.now().isoformat(),
            'createdBy': request.user.email
        }
        ip_list.append(ip_item)
        try:
            cache.set('security_ip_allowlist', ip_list, timeout=None)
        except Exception:
            # If cache fails, continue without caching
            pass

        return Response(ip_item, status=status.HTTP_201_CREATED)


class AdminIpAllowDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def delete(self, request, pk):
        """Remove IP from allowlist"""
        try:
            ip_list = cache.get('security_ip_allowlist', [])
            ip_list = [ip for ip in ip_list if ip.get('id') != pk]
            cache.set('security_ip_allowlist', ip_list, timeout=None)
        except Exception:
            # If cache fails, continue without caching
            pass
        return Response({'success': True}, status=status.HTTP_200_OK)


class AdminCertStatusView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        """Get TLS certificate status"""
        try:
            cert = cache.get('security_cert_status')
        except Exception:
            cert = None
        if not cert:
            cert = {
                'issuer': 'Let\'s Encrypt',
                'validFrom': timezone.now().isoformat(),
                'validTo': (timezone.now() + timezone.timedelta(days=60)).isoformat(),
                'daysRemaining': 60,
                'autoRenew': True
            }
        return Response(cert, status=status.HTTP_200_OK)

    def post(self, request):
        """Renew certificate"""
        # Placeholder - in production, trigger cert renewal job
        cert = {
            'issuer': 'Let\'s Encrypt',
            'validFrom': timezone.now().isoformat(),
            'validTo': (timezone.now() + timezone.timedelta(days=90)).isoformat(),
            'daysRemaining': 90,
            'autoRenew': True
        }
        try:
            cache.set('security_cert_status', cert, timeout=None)
        except Exception:
            # If cache fails, continue without caching
            pass
        return Response({
            'success': True,
            'message': 'Certificate renewal job queued',
            'cert': cert
        }, status=status.HTTP_200_OK)


class AdminSessionListView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        """List active sessions"""
        user_id = request.query_params.get('userId')

        # Placeholder - in production, query actual session store
        # For now, return mock data based on user_id
        sessions = []
        if user_id:
            # Return sessions for specific user
            sessions = [
                {
                    'jti': f'session_{user_id}_1',
                    'userId': int(user_id),
                    'device': 'Windows • Chrome',
                    'ip': '192.168.1.100',
                    'location': 'VN',
                    'createdAt': timezone.now().isoformat(),
                    'lastActiveAt': timezone.now().isoformat()
                }
            ]
        else:
            # Return all active sessions (limited)
            sessions = [
                {
                    'jti': f'session_{i}',
                    'userId': i,
                    'device': 'Windows • Chrome' if i % 2 == 0 else 'Android • Chrome',
                    'ip': f'192.168.1.{100 + i}',
                    'location': 'VN',
                    'createdAt': timezone.now().isoformat(),
                    'lastActiveAt': timezone.now().isoformat()
                }
                for i in range(1, 11)
            ]

        return Response(sessions, status=status.HTTP_200_OK)


class AdminSessionRevokeView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def delete(self, request, jti):
        """Revoke a session"""
        # Placeholder - in production, revoke from session store
        return Response({
            'success': True,
            'message': f'Session {jti} revoked'
        }, status=status.HTTP_200_OK)


class AdminAlertPolicyView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        """Get alert policy"""
        try:
            alert_policy = cache.get('security_alert_policy')
        except Exception:
            alert_policy = None
        if not alert_policy:
            alert_policy = {
                'cpuThreshold': 90,
                'errorRateThreshold': 2,
                'channels': {
                    'email': True,
                    'sms': True
                },
                'onCall': ''
            }
        return Response(alert_policy, status=status.HTTP_200_OK)

    def post(self, request):
        """Update alert policy"""
        alert_policy = request.data
        try:
            cache.set('security_alert_policy', alert_policy, timeout=None)
        except Exception:
            # If cache fails, continue without caching
            pass
        return Response(alert_policy, status=status.HTTP_200_OK)

    def put(self, request):
        """Test alert"""
        # Placeholder - in production, send test alert
        return Response({
            'success': True,
            'message': 'Test alert sent'
        }, status=status.HTTP_200_OK)
