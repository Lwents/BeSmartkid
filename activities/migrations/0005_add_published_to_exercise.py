# Generated manually
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0004_exercisesettings_scheduled_at_end_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='exercise',
            name='published',
            field=models.BooleanField(default=False),
        ),
    ]


