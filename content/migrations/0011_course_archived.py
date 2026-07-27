from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('content', '0010_course_timestamps'),
    ]

    operations = [
        migrations.AddField(
            model_name='course',
            name='archived',
            field=models.BooleanField(default=False),
        ),
    ]
