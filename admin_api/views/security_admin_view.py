from datetime import timedelta
from django.core.cache import cache
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from admin_api.permissions import IsAdmin
from admin_api.services import record_admin_action
from custom_account.models import SecurityPolicy, UserSession


class AdminSecurityPolicyView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    INTEGER_RANGES = {
        'rateLimit.loginFailures': (1, 50),
        'rateLimit.windowMin': (1, 1440),
        'lockout.attempts': (1, 50),
        'lockout.lockMinutes': (1, 10080),
        'lockout.banStrikes': (1, 50),
    }

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
        errors = self._validate_payload(payload)
        if errors:
            return Response(
                {
                    'detail': 'Một số chính sách bảo mật chưa hợp lệ.',
                    'errors': errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        policy = SecurityPolicy.get_current()

        twofa = payload.get('twoFA') or {}
        rate_limit = payload.get('rateLimit') or {}
        lockout = payload.get('lockout') or {}

        if isinstance(twofa, dict):
            if 'enforceAdmin' in twofa:
                policy.twofa_enforce_admin = twofa.get('enforceAdmin')
            if 'enforceTeacher' in twofa:
                policy.twofa_enforce_teacher = twofa.get('enforceTeacher')

        if isinstance(rate_limit, dict):
            if 'loginFailures' in rate_limit:
                policy.rate_limit_login_failures = rate_limit.get('loginFailures')
            if 'windowMin' in rate_limit:
                policy.rate_limit_window_min = rate_limit.get('windowMin')

        if isinstance(lockout, dict):
            if 'attempts' in lockout:
                policy.lockout_attempts = lockout.get('attempts')
            if 'lockMinutes' in lockout:
                policy.lockout_minutes = lockout.get('lockMinutes')
            if 'banStrikes' in lockout:
                policy.lockout_ban_strikes = lockout.get('banStrikes')

        if 'rbacNote' in payload:
            policy.rbac_note = payload.get('rbacNote') or ''

        policy.save()
        record_admin_action(
            request=request,
            action='security.policy.update',
            target_type='security_policy',
            target_id=policy.pk,
        )

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

    patch = post

    def _validate_payload(self, payload):
        errors = {}
        if not isinstance(payload, dict):
            return {'policy': 'Chính sách phải là một nhóm giá trị.'}
        allowed = {'twoFA', 'rateLimit', 'lockout', 'rbacNote'}
        for key in payload:
            if key not in allowed:
                errors[key] = 'Trường chính sách không được hỗ trợ.'

        twofa = payload.get('twoFA')
        if twofa is not None:
            self._validate_group(twofa, 'twoFA', {'enforceAdmin', 'enforceTeacher'}, errors)
            if isinstance(twofa, dict):
                for key, value in twofa.items():
                    if key in {'enforceAdmin', 'enforceTeacher'} and not isinstance(value, bool):
                        errors[f'twoFA.{key}'] = 'Giá trị phải là bật hoặc tắt.'

        for group_name, allowed_keys in (
            ('rateLimit', {'loginFailures', 'windowMin'}),
            ('lockout', {'attempts', 'lockMinutes', 'banStrikes'}),
        ):
            group = payload.get(group_name)
            if group is None:
                continue
            self._validate_group(group, group_name, allowed_keys, errors)
            if not isinstance(group, dict):
                continue
            for key, value in group.items():
                path = f'{group_name}.{key}'
                if key not in allowed_keys:
                    continue
                if not isinstance(value, int) or isinstance(value, bool):
                    errors[path] = 'Giá trị phải là số nguyên.'
                    continue
                lower, upper = self.INTEGER_RANGES[path]
                if value < lower or value > upper:
                    errors[path] = f'Giá trị phải từ {lower} đến {upper}.'

        if 'rbacNote' in payload:
            note = payload.get('rbacNote')
            if not isinstance(note, str):
                errors['rbacNote'] = 'Ghi chú phải là văn bản.'
            elif len(note) > 1000:
                errors['rbacNote'] = 'Ghi chú không được vượt quá 1000 ký tự.'
        return errors

    def _validate_group(self, value, name, allowed_keys, errors):
        if not isinstance(value, dict):
            errors[name] = 'Phần chính sách này phải là một nhóm giá trị.'
            return
        for key in value:
            if key not in allowed_keys:
                errors[f'{name}.{key}'] = 'Trường chính sách không được hỗ trợ.'


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
        self._sync_outstanding_tokens()
        sessions = UserSession.objects.filter(
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
        ).select_related('user')
        if user_id:
            sessions = sessions.filter(user_id=user_id)
        return Response([
            {
                'jti': item.jti,
                'userId': item.user_id,
                'userEmail': item.user.email,
                'device': item.device or 'Thiết bị chưa xác định',
                'ip': item.ip_address or 'Không rõ',
                'location': '',
                'createdAt': item.created_at.isoformat(),
                'lastActiveAt': item.last_active_at.isoformat(),
                'expiresAt': item.expires_at.isoformat(),
            }
            for item in sessions[:100]
        ], status=status.HTTP_200_OK)

    def _sync_outstanding_tokens(self):
        now = timezone.now()
        tokens = OutstandingToken.objects.filter(
            expires_at__gt=now,
            user__isnull=False,
        ).select_related('user')
        blacklisted_ids = set(
            BlacklistedToken.objects.filter(token__in=tokens)
            .values_list('token_id', flat=True)
        )
        for token in tokens:
            if token.id in blacklisted_ids:
                UserSession.objects.filter(jti=token.jti, revoked_at__isnull=True).update(
                    revoked_at=now
                )
                continue
            UserSession.objects.get_or_create(
                jti=token.jti,
                defaults={
                    'user': token.user,
                    'device': 'Thiết bị chưa xác định',
                    'created_at': token.created_at,
                    'last_active_at': token.created_at,
                    'expires_at': token.expires_at,
                },
            )


class AdminSessionRevokeView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def delete(self, request, jti):
        """Revoke a session"""
        session = UserSession.objects.filter(jti=jti).select_related('user').first()
        token = OutstandingToken.objects.filter(jti=jti).first()
        if not session and not token:
            return Response(
                {'detail': 'Không tìm thấy phiên đăng nhập.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        if token:
            BlacklistedToken.objects.get_or_create(token=token)
        now = timezone.now()
        if session and not session.revoked_at:
            session.revoked_at = now
            session.save(update_fields=['revoked_at'])
        record_admin_action(
            request=request,
            action='security.session.revoke',
            target_type='user_session',
            target_id=jti,
            details={'userId': session.user_id if session else token.user_id},
        )
        return Response({
            'success': True,
            'message': 'Đã thu hồi phiên đăng nhập.'
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
