from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0011_exercise_grade'),
    ]

    operations = [
        migrations.AddField(
            model_name='exercisesettings',
            name='course_id',
            field=models.UUIDField(blank=True, null=True),
        ),
    ]
