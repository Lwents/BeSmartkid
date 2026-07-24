# Generated migration for new event fields

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('content', '0001_initial'),
        ('events', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='platformevent',
            name='description',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AlterField(
            model_name='platformevent',
            name='end_date',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='platformevent',
            name='type',
            field=models.CharField(
                choices=[
                    ('exam', 'Kiểm tra'),
                    ('quiz', 'Quiz'),
                    ('challenge', 'Thử thách'),
                    ('webinar', 'Webinar'),
                    ('meeting', 'Họp'),
                    ('deadline', 'Hạn nộp'),
                    ('other', 'Khác'),
                ],
                default='other',
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name='platformevent',
            name='status',
            field=models.CharField(
                choices=[
                    ('upcoming', 'Upcoming'),
                    ('ongoing', 'Ongoing'),
                    ('ended', 'Ended'),
                    ('cancelled', 'Cancelled'),
                ],
                default='upcoming',
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name='platformevent',
            name='created_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='created_events',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='platformevent',
            name='course',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='events',
                to='content.course',
            ),
        ),
        migrations.AddField(
            model_name='platformevent',
            name='notify_students',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='platformevent',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
        migrations.AddField(
            model_name='platformevent',
            name='updated_at',
            field=models.DateTimeField(auto_now=True, null=True),
        ),
    ]
