# Generated manually for LessonQuestionReaction
from django.db import migrations, models
import uuid
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0006_lesson_questions'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='LessonQuestionReaction',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('emoji', models.CharField(default='like', max_length=16)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('reply', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='reactions', to='activities.lessonquestionreply')),
                ('user', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='lesson_question_reactions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AlterUniqueTogether(
            name='lessonquestionreaction',
            unique_together={('reply', 'user')},
        ),
    ]
