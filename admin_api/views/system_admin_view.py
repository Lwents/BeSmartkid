import shutil
from uuid import UUID
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from admin_api.permissions import IsAdmin
from admin_api.models import AdminAuditLog, SystemBackup, SystemConfiguration
from admin_api.services import create_system_backup, record_admin_action

# Try to import psutil for system metrics, fallback to basic implementation
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


class AdminSystemConfigView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        """Get system configuration"""
        config, _ = SystemConfiguration.objects.get_or_create(
            pk=1,
            defaults={'data': self._get_default_config()},
        )
        return Response(self._serialize(config), status=status.HTTP_200_OK)

    def post(self, request):
        """Update system configuration"""
        if not isinstance(request.data, dict):
            return Response(
                {'detail': 'Cấu hình phải là một JSON object.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        payload = dict(request.data)
        payload.pop('version', None)
        payload.pop('updatedBy', None)
        payload.pop('updatedAt', None)
        config, _ = SystemConfiguration.objects.get_or_create(pk=1)
        config.data = payload
        config.version += 1
        config.updated_by = request.user
        config.save()
        record_admin_action(
            request=request,
            action='system.config.update',
            target_type='system_configuration',
            target_id=config.pk,
            details={'version': config.version},
        )
        return Response(self._serialize(config), status=status.HTTP_200_OK)

    def _serialize(self, config):
        payload = dict(config.data or {})
        payload['version'] = config.version
        payload['updatedBy'] = config.updated_by.email if config.updated_by else ''
        payload['updatedAt'] = config.updated_at.isoformat()
        return payload

    def _get_default_config(self):
        """Get default system configuration"""
        return {
            'brand': {
                'siteName': getattr(settings, 'SITE_NAME', 'SmartKid'),
                'language': 'vi',
                'timezone': 'Asia/Ho_Chi_Minh',
                'currency': 'VND',
                'logoUrl': ''
            },
            'domainEmail': {
                'domain': getattr(settings, 'ALLOWED_HOSTS', ['localhost'])[0],
                'forceHttps': True,
                'hsts': True,
                'smtp': {
                    'host': getattr(settings, 'EMAIL_HOST', ''),
                    'port': getattr(settings, 'EMAIL_PORT', 587),
                    'username': getattr(settings, 'EMAIL_HOST_USER', ''),
                    'passwordMasked': bool(getattr(settings, 'EMAIL_HOST_PASSWORD', '')),
                    'senderName': getattr(settings, 'DEFAULT_FROM_NAME', ''),
                    'fromEmail': getattr(settings, 'DEFAULT_FROM_EMAIL', '')
                },
                'spf': {'status': 'unknown'},
                'dkim': {'status': 'unknown'},
                'dmarc': {'status': 'unknown'}
            },
            'authSession': {
                'idleTimeoutMin': 30,
                'maxSessionHours': 24,
                'rememberMeDays': 14,
                'ssoGoogleEnabled': False,
                'googleClientId': '',
                'twoFAEnforce': {'admin': True, 'teacher': False},
                'passwordPolicy': {
                    'minLength': 8,
                    'requireNumbers': True,
                    'requireSymbols': True
                },
                'singleDeviceOnly': True
            },
            'backup': {
                'schedule': 'daily',
                'retentionDays': 30,
                'rpoMinutes': 15,
                'rtoMinutes': 120,
                'encrypted': True
            },
            'maintenance': {
                'enabled': False,
                'window': {
                    'dayOfWeek': 0,
                    'start': '01:00',
                    'end': '03:00'
                }
            },
            'integrations': {
                'payments': {
                    'momo': True,
                    'vnpay': True,
                    'qr': True,
                    'bank': True
                },
                'analytics': {
                    'ga4MeasurementId': ''
                },
                'zoom': {
                    'enabled': False
                },
                'storage': {
                    'provider': 'local',
                    'bucket': '',
                    'region': ''
                }
            },
            'logging': {
                'level': 'info',
                'retentionDays': 90,
                'traceIdEnabled': True
            },
            'version': 0,
            'updatedBy': '',
            'updatedAt': timezone.now().isoformat()
        }


class AdminSystemBackupView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        """List backups"""
        backups = [self._serialize(item) for item in SystemBackup.objects.all()[:20]]
        return Response(backups, status=status.HTTP_200_OK)

    def post(self, request):
        """Create backup"""
        try:
            backup = create_system_backup(
                user=request.user,
                notes=request.data.get('notes') or 'Sao lưu thủ công',
            )
            record_admin_action(
                request=request,
                action='system.backup.create',
                target_type='system_backup',
                target_id=backup.id,
                details={'fileName': backup.file_name, 'sizeBytes': backup.size_bytes},
            )
            return Response(self._serialize(backup), status=status.HTTP_201_CREATED)
        except Exception as exc:
            record_admin_action(
                request=request,
                action='system.backup.create',
                target_type='system_backup',
                status='failed',
                details={'error': str(exc)},
            )
            return Response(
                {'detail': f'Không thể tạo bản sao lưu: {exc}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _serialize(self, backup):
        return {
            'id': str(backup.id),
            'title': f'Sao lưu {backup.created_at:%d/%m/%Y %H:%M}',
            'fileName': backup.file_name,
            'createdAt': backup.created_at.isoformat(),
            'sizeBytes': backup.size_bytes,
            'sizeMB': round(backup.size_bytes / (1024 * 1024), 2),
            'checksum': backup.checksum,
            'notes': backup.notes,
            'status': backup.status,
        }


class AdminSystemRestoreView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request):
        """Restore from backup"""
        backup_id = request.data.get('backupId')

        if not backup_id:
            return Response({'error': 'backupId required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            parsed_backup_id = UUID(str(backup_id))
        except (TypeError, ValueError, AttributeError):
            return Response(
                {'detail': 'Mã bản sao lưu không hợp lệ.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        backup = SystemBackup.objects.filter(pk=parsed_backup_id).first()
        if not backup:
            return Response(
                {'detail': 'Không tìm thấy bản sao lưu.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({
            'detail': (
                'Chưa thể khôi phục tự động an toàn khi hệ thống đang hoạt động. '
                'Hãy thực hiện trong chế độ bảo trì.'
            )
        }, status=status.HTTP_501_NOT_IMPLEMENTED)


class AdminSystemAuditView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        """Get persisted system audit log"""
        audits = [
            {
                'id': str(item.id),
                'action': item.action,
                'userEmail': item.actor.email if item.actor else '',
                'timestamp': item.created_at.isoformat(),
                'status': item.status,
                'details': item.details,
            }
            for item in AdminAuditLog.objects.all()[:100]
        ]
        return Response(audits, status=status.HTTP_200_OK)


class AdminSystemTestEmailView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request):
        """Send test email"""
        email = request.data.get('email')

        if not email:
            return Response({'error': 'email required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            send_mail(
                subject='Test Email from SmartKid',
                message='This is a test email from the SmartKid admin panel.',
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com'),
                recipient_list=[email],
                fail_silently=False
            )
            return Response({'success': True, 'message': 'Test email sent'}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminSystemHealthView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        """Get system health metrics (CPU, RAM, Disk, Backup status)"""
        try:
            # Get CPU usage
            if HAS_PSUTIL:
                cpu_percent = psutil.cpu_percent(interval=1)
                cpu_percent_p95 = self._get_cpu_p95()
            else:
                # Fallback: try to read from /proc/loadavg on Linux
                try:
                    with open('/proc/loadavg', 'r') as f:
                        loadavg = f.read().split()
                        # Convert load average to approximate CPU percentage
                        cpu_percent = min(float(loadavg[0]) * 25, 100)  # Rough estimate
                        cpu_percent_p95 = cpu_percent
                except:
                    cpu_percent = 0
                    cpu_percent_p95 = 0

            # Get RAM usage
            if HAS_PSUTIL:
                memory = psutil.virtual_memory()
                ram_percent = memory.percent
                ram_percent_p95 = ram_percent  # Could implement p95 tracking
            else:
                # Fallback: try to read from /proc/meminfo on Linux
                try:
                    with open('/proc/meminfo', 'r') as f:
                        meminfo = {}
                        for line in f:
                            parts = line.split()
                            if len(parts) >= 2:
                                meminfo[parts[0].rstrip(':')] = int(parts[1])
                    
                    total = meminfo.get('MemTotal', 0)
                    available = meminfo.get('MemAvailable', meminfo.get('MemFree', 0))
                    if total > 0:
                        ram_percent = ((total - available) / total) * 100
                    else:
                        ram_percent = 0
                    ram_percent_p95 = ram_percent
                except:
                    ram_percent = 0
                    ram_percent_p95 = 0

            # Get Disk usage
            if HAS_PSUTIL:
                disk = psutil.disk_usage('/')
                disk_percent = disk.percent
            else:
                # Fallback: use shutil
                try:
                    disk = shutil.disk_usage('/')
                    if disk.total > 0:
                        disk_percent = (disk.used / disk.total) * 100
                    else:
                        disk_percent = 0
                except:
                    disk_percent = 0

            last_backup = SystemBackup.objects.first()
            backup_status = last_backup.status if last_backup else 'no_backup'
            backup_time = last_backup.created_at.isoformat() if last_backup else ''

            return Response({
                'cpu': {
                    'current': round(cpu_percent, 1),
                    'p95': round(cpu_percent_p95, 1)
                },
                'ram': {
                    'current': round(ram_percent, 1),
                    'p95': round(ram_percent_p95, 1)
                },
                'disk': {
                    'current': round(disk_percent, 1)
                },
                'backup': {
                    'status': backup_status,
                    'lastBackup': backup_time
                }
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'error': str(e),
                'cpu': {'current': 0, 'p95': 0},
                'ram': {'current': 0, 'p95': 0},
                'disk': {'current': 0},
                'backup': {'status': 'error', 'lastBackup': ''}
            }, status=status.HTTP_200_OK)

    def _get_cpu_p95(self):
        """Get CPU p95 value (simplified - could implement proper tracking)"""
        # In production, you'd track CPU usage over time and calculate p95
        # For now, return current value as approximation
        if HAS_PSUTIL:
            return psutil.cpu_percent(interval=0.1)
        return 0
