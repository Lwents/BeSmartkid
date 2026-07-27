import gzip
import hashlib
import uuid
from pathlib import Path

from django.conf import settings
from django.core.management import call_command

from admin_api.models import AdminAuditLog, SystemBackup
from custom_account.services.login_security_service import get_client_ip


def record_admin_action(
    *, request, action, target_type='', target_id='', status='success', details=None
):
    return AdminAuditLog.objects.create(
        actor=getattr(request, 'user', None) if getattr(request, 'user', None) and request.user.is_authenticated else None,
        action=action,
        target_type=target_type,
        target_id=str(target_id or ''),
        status=status,
        ip_address=get_client_ip(request) if request else None,
        user_agent=request.META.get('HTTP_USER_AGENT', '') if request else '',
        details=details or {},
    )


def create_system_backup(*, user, notes='') -> SystemBackup:
    backup_id = uuid.uuid4()
    backup = SystemBackup.objects.create(
        id=backup_id,
        file_name=f'pending-{backup_id}.json.gz',
        status=SystemBackup.STATUS_FAILED,
        notes=notes or 'Sao lưu thủ công',
        created_by=user,
    )
    file_name = f'smartkid-{backup.created_at:%Y%m%d-%H%M%S}-{backup.id}.json.gz'
    backup.file_name = file_name
    target_dir = Path(settings.MEDIA_ROOT) / 'system_backups'
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / file_name
    try:
        with gzip.open(target, 'wt', encoding='utf-8') as output:
            call_command(
                'dumpdata',
                exclude=[
                    'admin_api.systembackup',
                    'contenttypes',
                    'auth.permission',
                    'sessions.session',
                    'token_blacklist.outstandingtoken',
                    'token_blacklist.blacklistedtoken',
                ],
                indent=2,
                stdout=output,
            )
        digest = hashlib.sha256()
        with target.open('rb') as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b''):
                digest.update(chunk)
        backup.size_bytes = target.stat().st_size
        backup.checksum = digest.hexdigest()
        backup.status = SystemBackup.STATUS_COMPLETED
        backup.save(update_fields=['file_name', 'size_bytes', 'checksum', 'status'])
        return backup
    except Exception:
        target.unlink(missing_ok=True)
        backup.file_name = file_name
        backup.status = SystemBackup.STATUS_FAILED
        backup.save(update_fields=['file_name', 'status'])
        raise
