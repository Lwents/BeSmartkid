"""
Management command to publish scheduled exercises and close expired ones.
Run this periodically (e.g., via cron) to automatically:
1. Publish exercises that have reached their scheduled_at time
2. Close exercises that have reached their end_at time

Usage:
    python manage.py publish_scheduled_exercises
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.apps import apps
from django.db import transaction


class Command(BaseCommand):
    help = 'Publish scheduled exercises and close expired ones'

    def handle(self, *args, **options):
        ExerciseModel = apps.get_model('activities', 'Exercise')
        ExerciseSettingsModel = apps.get_model('activities', 'ExerciseSettings')
        
        now = timezone.now()
        
        # 1. Find exercises with scheduled_at <= now and not yet published
        scheduled_settings = ExerciseSettingsModel.objects.filter(
            scheduled_at__isnull=False,
            scheduled_at__lte=now,
            exercise__published=False
        ).select_related('exercise')
        
        published_count = 0
        for settings in scheduled_settings:
            with transaction.atomic():
                exercise = settings.exercise
                exercise.published = True
                exercise.save(update_fields=['published'])
                
                # Clear scheduled_at after publishing
                settings.scheduled_at = None
                settings.save(update_fields=['scheduled_at'])
                
                published_count += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Published exercise "{exercise.title}" (ID: {exercise.id})'
                    )
                )
        
        # 2. Find exercises with end_at <= now and still published
        expired_settings = ExerciseSettingsModel.objects.filter(
            end_at__isnull=False,
            end_at__lte=now,
            exercise__published=True
        ).select_related('exercise')
        
        closed_count = 0
        for settings in expired_settings:
            with transaction.atomic():
                exercise = settings.exercise
                exercise.published = False
                exercise.save(update_fields=['published'])
                
                # Clear end_at after closing
                settings.end_at = None
                settings.save(update_fields=['end_at'])
                
                closed_count += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Closed exercise "{exercise.title}" (ID: {exercise.id})'
                    )
                )
        
        if published_count == 0 and closed_count == 0:
            self.stdout.write(self.style.SUCCESS('No exercises to publish or close'))
        else:
            if published_count > 0:
                self.stdout.write(
                    self.style.SUCCESS(f'Successfully published {published_count} exercise(s)')
                )
            if closed_count > 0:
                self.stdout.write(
                    self.style.SUCCESS(f'Successfully closed {closed_count} exercise(s)')
                )

