# Generated manually
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0003_notification_teacherfeedback'),
    ]

    operations = [
        migrations.AddField(
            model_name='exercisesettings',
            name='scheduled_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='When to automatically publish'),
        ),
        migrations.AddField(
            model_name='exercisesettings',
            name='end_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='When to automatically close the exam'),
        ),
    ]


