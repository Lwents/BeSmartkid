# celeryconfig.py (project root)
"""
Celery configuration for async task processing.
"""
from celery import Celery
from celery.schedules import crontab
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

app = Celery('backend')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Periodic task schedule
app.conf.beat_schedule = {
    'update-skill-decay-daily': {
        'task': 'ai_personalization.tasks.batch_update_skill_decay',
        'schedule': crontab(hour=2, minute=0),  # Daily at 2 AM
    },
    'train-mastery-model-weekly': {
        'task': 'ai_personalization.tasks.train_mastery_prediction_model',
        'schedule': crontab(day_of_week=1, hour=3, minute=0),  # Weekly Monday 3 AM
    },
    # Streak Warning - Chạy mỗi giờ từ 21:00-22:00
    'send-streak-warnings': {
        'task': 'ai_personalization.tasks.send_streak_warning_notifications',
        'schedule': crontab(hour='21-22', minute=0),  # Mỗi giờ từ 21:00-22:00
    },
    # Come Back Reminder - Chạy mỗi ngày lúc 10:00
    'send-comeback-reminders': {
        'task': 'ai_personalization.tasks.send_comeback_reminders',
        'schedule': crontab(hour=10, minute=0),  # Daily at 10 AM
    },
    # Come Back Email - Chạy mỗi ngày lúc 10:30
    'send-comeback-emails': {
        'task': 'ai_personalization.tasks.send_comeback_emails',
        'schedule': crontab(hour=10, minute=30),  # Daily at 10:30 AM
    },
    # Auto Restore Streak & Award Badges - Chạy mỗi ngày lúc 0:05 (sau khi streak được tính lại)
    'auto-restore-streak-badges': {
        'task': 'ai_personalization.tasks.auto_restore_streak_and_award_badges',
        'schedule': crontab(hour=0, minute=5),  # Daily at 00:05 AM
    },
}