import shutil
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from uuid import UUID
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.core.paginator import Paginator
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from admin_api.permissions import IsAdmin
from admin_api.models import AdminAuditLog, SystemBackup, SystemConfiguration
from admin_api.services import create_system_backup, record_admin_action
from admin_api.pagination import page_link, positive_int_query
from admin_api.runtime_config import invalidate_runtime_config, timezone_name
from infrastructure.email_service import get_email_service

# Try to import psutil for system metrics, fallback to basic implementation
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


class AdminSystemConfigView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    INTEGER_RANGES = {
        'domainEmail.smtp.port': (1, 65535),
        'authSession.idleTimeoutMin': (1, 1440),
        'authSession.maxSessionHours': (1, 720),
        'authSession.rememberMeDays': (0, 365),
        'authSession.passwordPolicy.minLength': (6, 128),
        'backup.retentionDays': (1, 3650),
        'backup.rpoMinutes': (1, 10080),
        'backup.rtoMinutes': (1, 10080),
        'maintenance.window.dayOfWeek': (0, 6),
        'logging.retentionDays': (1, 3650),
    }
    CHOICES = {
        'brand.language': {'vi', 'en'},
        'brand.currency': {'VND', 'USD'},
        'backup.schedule': {'daily', 'weekly', 'manual'},
        'integrations.storage.provider': {'local', 's3'},
        'logging.level': {'debug', 'info', 'warning', 'error'},
    }
    REQUIRED_STRINGS = {
        'brand.siteName', 'brand.language', 'brand.timezone', 'brand.currency',
        'domainEmail.domain',
    }

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
        errors = {}
        self._validate_node(payload, self._get_default_config(), '', errors)
        if errors:
            return Response(
                {
                    'detail': 'Một số cấu hình chưa hợp lệ. Vui lòng kiểm tra lại.',
                    'errors': errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        config, _ = SystemConfiguration.objects.get_or_create(
            pk=1,
            defaults={'data': self._get_default_config()},
        )
        config.data = self._without_legacy_payments(
            self._deep_merge(
                self._deep_merge(self._get_default_config(), config.data or {}),
                payload,
            )
        )
        config.version += 1
        config.updated_by = request.user
        config.save()
        invalidate_runtime_config()
        record_admin_action(
            request=request,
            action='system.config.update',
            target_type='system_configuration',
            target_id=config.pk,
            details={'version': config.version},
        )
        return Response(self._serialize(config), status=status.HTTP_200_OK)

    patch = post

    def _serialize(self, config):
        payload = self._without_legacy_payments(
            self._deep_merge(self._get_default_config(), config.data or {})
        )
        payload['version'] = config.version
        payload['updatedBy'] = config.updated_by.email if config.updated_by else ''
        payload['updatedAt'] = config.updated_at.isoformat()
        return payload

    def _validate_node(self, value, schema, path, errors):
        if not isinstance(value, dict):
            errors[path or 'config'] = 'Phần cấu hình này phải là một nhóm giá trị.'
            return
        for key, child in value.items():
            child_path = f'{path}.{key}' if path else key
            if key not in schema:
                errors[child_path] = 'Trường cấu hình không được hỗ trợ.'
                continue
            expected = schema[key]
            if isinstance(expected, dict):
                self._validate_node(child, expected, child_path, errors)
            else:
                self._validate_scalar(child, expected, child_path, errors)

    def _validate_scalar(self, value, expected, path, errors):
        if isinstance(expected, bool):
            if not isinstance(value, bool):
                errors[path] = 'Giá trị phải là bật hoặc tắt.'
            return
        if isinstance(expected, int):
            if not isinstance(value, int) or isinstance(value, bool):
                errors[path] = 'Giá trị phải là số nguyên.'
                return
            lower, upper = self.INTEGER_RANGES.get(path, (0, 1000000))
            if value < lower or value > upper:
                errors[path] = f'Giá trị phải từ {lower} đến {upper}.'
            return
        if not isinstance(value, str):
            errors[path] = 'Giá trị phải là văn bản.'
            return
        normalized = value.strip()
        if path in self.REQUIRED_STRINGS and not normalized:
            errors[path] = 'Không được để trống.'
        elif len(value) > 1000:
            errors[path] = 'Nội dung không được vượt quá 1000 ký tự.'
        elif path in self.CHOICES and value not in self.CHOICES[path]:
            errors[path] = 'Giá trị không nằm trong danh sách được hỗ trợ.'
        elif path in {'maintenance.window.start', 'maintenance.window.end'} \
                and not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value):
            errors[path] = 'Thời gian phải theo định dạng HH:mm.'
        elif path == 'domainEmail.smtp.fromEmail' and normalized:
            try:
                validate_email(normalized)
            except DjangoValidationError:
                if not re.fullmatch(r'[^@\s]+@[A-Za-z0-9-]+', normalized):
                    errors[path] = 'Địa chỉ email chưa hợp lệ.'

    def _deep_merge(self, base, patch):
        merged = dict(base or {})
        for key, value in (patch or {}).items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = self._deep_merge(merged[key], value)
            else:
                merged[key] = value
        return merged

    def _without_legacy_payments(self, data):
        cleaned = dict(data or {})
        integrations = dict(cleaned.get('integrations') or {})
        integrations.pop('payments', None)
        cleaned['integrations'] = integrations
        return cleaned

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
        }


class AdminSystemBackupView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        """List backups"""
        page = positive_int_query(request, 'page', 1)
        page_size = positive_int_query(
            request, 'pageSize', 20, aliases=('page_size',), maximum=100
        )
        paginator = Paginator(SystemBackup.objects.all(), page_size)
        if page > max(paginator.num_pages, 1):
            return Response(
                {'page': 'Trang yêu cầu vượt quá số trang hiện có.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        page_obj = paginator.page(page)
        backups = [self._serialize(item) for item in page_obj]
        return Response({
            'results': backups,
            'backups': backups,
            'count': paginator.count,
            'page': page,
            'page_size': page_size,
            'total_pages': paginator.num_pages,
            'next': page_link(request, page + 1) if page_obj.has_next() else None,
            'previous': page_link(request, page - 1) if page_obj.has_previous() else None,
        }, status=status.HTTP_200_OK)

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
        try:
            created_at = timezone.localtime(backup.created_at, ZoneInfo(timezone_name()))
        except ZoneInfoNotFoundError:
            created_at = timezone.localtime(backup.created_at)
        return {
            'id': str(backup.id),
            'title': f'Sao lưu {created_at:%d/%m/%Y %H:%M}',
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
            return Response({'detail': 'Vui lòng nhập email nhận thư kiểm tra.'},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            validate_email(email)
        except DjangoValidationError:
            return Response({'detail': 'Địa chỉ email chưa hợp lệ.'},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            get_email_service().send(
                to=email,
                subject='SmartKid - Kiểm tra cấu hình email',
                body='Email máy chủ SmartKid đã được cấu hình và gửi thành công.',
            )
            record_admin_action(
                request=request,
                action='system.email.test',
                target_type='email',
                details={'recipient': email},
            )
            return Response(
                {'success': True, 'detail': 'Đã gửi email kiểm tra.'},
                status=status.HTTP_200_OK,
            )
        except Exception:
            record_admin_action(
                request=request,
                action='system.email.test',
                target_type='email',
                status='failed',
                details={'recipient': email},
            )
            return Response(
                {'detail': 'Không gửi được email. Hãy kiểm tra SMTP và mật khẩu ứng dụng trên máy chủ.'},
                status=status.HTTP_502_BAD_GATEWAY,
            )


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
