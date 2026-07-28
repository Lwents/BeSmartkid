import os
from datetime import datetime, timedelta
from django.core.cache import cache
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from admin_api.permissions import IsAdmin
from admin_api.models import SystemBackup
from custom_account.models import UserModel, AuthAttempt, UserPresence
from content.models import Course, Lesson

try:
    import psutil  # type: ignore
except ImportError:  # pragma: no cover - psutil might be absent in some envs
    psutil = None


class AdminDashboardView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        """Get dashboard KPIs and stats"""
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_ago = now - timedelta(days=7)

        # DAU (Daily Active Users) - users who logged in today
        dau = UserModel.objects.filter(
            last_login__gte=today_start
        ).count()

        # New signups in last 7 days
        signups7d = UserModel.objects.filter(
            created_on__gte=week_ago
        ).count()

        students = UserModel.objects.filter(role='student', is_active=True).count()
        teachers = UserModel.objects.filter(role='instructor', is_active=True).count()
        courses = Course.objects.count()
        lessons = Lesson.objects.count()

        # Top courses by enrollments
        top_courses = Course.objects.filter(
            published=True
        ).annotate(
            enrollments_count=Count('enrollments', distinct=True)
        ).order_by('-enrollments_count', 'title')[:5]

        top_courses_data = [
            {
                'id': str(course.id),
                'title': course.title,
                'enrollments': course.enrollments_count
            }
            for course in top_courses
        ]

        security = self._get_security_stats(now)
        system = self._get_system_health()
        active_users = self._get_active_users(now)

        return Response({
            'kpis': {
                'dau': dau,
                'signups7d': signups7d,
                'students': students,
                'teachers': teachers,
                'courses': courses,
                'lessons': lessons,
            },
            'topCourses': top_courses_data,
            'activeUsers': active_users,
            'security': security,
            'system': system
        }, status=status.HTTP_200_OK)

    def _get_security_stats(self, now: datetime) -> dict:
        window_start = now - timedelta(hours=24)
        failed_logins = AuthAttempt.objects.filter(
            success=False,
            created_at__gte=window_start,
        ).count()
        locked_accounts = UserModel.objects.filter(
            Q(is_active=False) | Q(lockout_until__gt=now)
        ).count()

        cert = cache.get('security_cert_status')
        days_to_expire = None
        if cert and cert.get('validTo'):
            try:
                valid_to = datetime.fromisoformat(cert['validTo'])
                days_to_expire = max((valid_to - now).days, 0)
            except Exception:
                days_to_expire = None

        return {
            'failedLogins24h': failed_logins,
            'lockedAccounts': locked_accounts,
            'sslDaysToExpire': days_to_expire if days_to_expire is not None else 0,
        }

    def _get_system_health(self) -> dict:
        cpu = ram = disk = None
        if psutil:
            try:
                cpu = psutil.cpu_percent(interval=0.1)
                ram = psutil.virtual_memory().percent
                disk = psutil.disk_usage('/').percent
            except Exception:
                cpu = ram = disk = None

        # Container không cài psutil -> đọc trực tiếp từ /proc như endpoint
        # /admin/system/health/, nếu không thẻ "Sức khỏe hệ thống" luôn hiện 0%.
        if cpu is None:
            try:
                with open('/proc/loadavg', 'r') as handle:
                    cpu = min(float(handle.read().split()[0]) * 25, 100)
            except Exception:
                cpu = None
        if ram is None:
            try:
                info = {}
                with open('/proc/meminfo', 'r') as handle:
                    for line in handle:
                        parts = line.split()
                        if len(parts) >= 2:
                            info[parts[0].rstrip(':')] = int(parts[1])
                total = info.get('MemTotal', 0)
                available = info.get('MemAvailable', info.get('MemFree', 0))
                if total:
                    ram = round((total - available) / total * 100, 2)
            except Exception:
                ram = None
        if disk is None:
            try:
                stats = os.statvfs('/')
                total_blocks = stats.f_blocks
                if total_blocks:
                    used = total_blocks - stats.f_bfree
                    disk = round(used / total_blocks * 100, 2)
            except Exception:
                disk = None

        latest_backup = SystemBackup.objects.order_by('-created_at').first()

        return {
            'cpuP95': round(cpu, 2) if cpu is not None else None,
            'ramP95': round(ram, 2) if ram is not None else None,
            'disk': round(disk, 2) if disk is not None else None,
            'backup': {
                'lastRun': latest_backup.created_at.isoformat() if latest_backup else None,
                'status': latest_backup.status if latest_backup else 'no_backup',
            },
        }

    def _get_active_users(self, now: datetime) -> dict:
        """Return users active within last 10 minutes."""
        threshold = now - timedelta(minutes=10)
        qs = UserPresence.objects.filter(
            last_seen_at__gte=threshold,
            user__is_active=True,
        ).exclude(
            Q(user__is_staff=True) | Q(user__role__iexact='admin')
        ).select_related('user', 'user__profile').order_by('-last_seen_at')

        recent = []
        for presence in qs[:15]:
            user = presence.user
            # getattr trực tiếp trên user: user không có profile sẽ trả None thay vì raise
            profile = getattr(user, 'profile', None)
            display_name = getattr(profile, 'display_name', None) if profile else None
            name = display_name or user.email or user.username
            recent.append({
                'id': str(user.id),
                'name': name,
                'email': user.email,
                'role': user.role,
                'roleLabel': self._role_label(user.role),
                'lastActive': presence.last_seen_at.isoformat(),
            })

        return {
            'count': qs.count(),
            'recent': recent,
            'windowMinutes': 10,
        }

    def _role_label(self, role: str | None) -> str:
        mapping = {
            'admin': 'Quản trị viên',
            'instructor': 'Giáo viên',
            'teacher': 'Giáo viên',
            'student': 'Học sinh',
        }
        if not role:
            return 'N/A'
        return mapping.get(role.lower(), role)


class AdminActiveUsersRealtimeView(AdminDashboardView):
    """Lightweight endpoint to fetch only active users for realtime updates."""

    def get(self, request):
        now = timezone.now()
        active_users = self._get_active_users(now)
        return Response(active_users, status=status.HTTP_200_OK)
