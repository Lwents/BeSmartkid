# Generated manually to add timestamps for Course.
from django.db import migrations, models
from django.utils import timezone


def backfill_course_timestamps(apps, schema_editor):
    Course = apps.get_model('content', 'Course')
    now = timezone.now()
    Course.objects.filter(created_on__isnull=True).update(created_on=now)
    Course.objects.filter(updated_on__isnull=True).update(updated_on=now)


class Migration(migrations.Migration):

    dependencies = [
        ('content', '0009_lesson_video_transcript'),
    ]

    operations = [
        migrations.AddField(
            model_name='course',
            name='created_on',
            field=models.DateTimeField(auto_now_add=True, blank=True, null=True),
        ),
        migrations.AddField(
            model_name='course',
            name='updated_on',
            field=models.DateTimeField(auto_now=True, blank=True, null=True),
        ),
        migrations.RunPython(backfill_course_timestamps, migrations.RunPython.noop),
    ]
