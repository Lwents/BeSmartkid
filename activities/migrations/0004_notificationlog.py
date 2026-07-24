# Generated migration for NotificationLog model
from django.db import migrations, models
import django.db.models.deletion
import uuid
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('activities', '0011_exercise_grade'),
    ]

    operations = [
        migrations.CreateModel(
            name='NotificationLog',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('notification_type', models.CharField(choices=[('streak_warning', 'Streak Warning'), ('comeback_1day', 'Come Back 1 Day'), ('comeback_3days', 'Come Back 3 Days'), ('comeback_7days', 'Come Back 7 Days'), ('comeback_email_1day', 'Come Back Email 1 Day'), ('comeback_email_3days', 'Come Back Email 3 Days'), ('comeback_email_7days', 'Come Back Email 7 Days')], max_length=64)),
                ('sent_at', models.DateTimeField(auto_now_add=True)),
                ('sent_date', models.DateField(db_index=True)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notification_logs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Notification Log',
                'verbose_name_plural': 'Notification Logs',
                'ordering': ['-sent_at'],
            },
        ),
        migrations.AddIndex(
            model_name='notificationlog',
            index=models.Index(fields=['user', 'notification_type', 'sent_date'], name='activities__user_id_2_idx'),
        ),
        migrations.AddIndex(
            model_name='notificationlog',
            index=models.Index(fields=['user', '-sent_at'], name='activities__user_id_3_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='notificationlog',
            unique_together={('user', 'notification_type', 'sent_date')},
        ),
    ]

