# Generated migration for show_answers field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0009_alter_lessonquestionreaction_unique_together_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='exercisesettings',
            name='show_answers',
            field=models.CharField(
                choices=[
                    ('always', 'Luôn hiển thị sau khi nộp bài'),
                    ('after_duration', 'Chỉ hiển thị sau khi hết thời gian làm bài'),
                    ('after_end', 'Chỉ hiển thị sau khi hết hạn bài thi'),
                    ('never', 'Không hiển thị đáp án'),
                ],
                default='always',
                max_length=16,
            ),
        ),
    ]
