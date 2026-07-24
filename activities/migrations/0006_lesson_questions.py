# Generated manually for Lesson Q&A
from django.db import migrations, models
import uuid
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('content', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('activities', '0005_add_published_to_exercise'),
    ]

    operations = [
        migrations.CreateModel(
            name='LessonQuestion',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('content', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('lesson', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='questions', to='content.lesson')),
                ('student', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='lesson_questions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='LessonQuestionReply',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('content', models.TextField()),
                ('is_teacher', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('question', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='replies', to='activities.lessonquestion')),
                ('user', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='lesson_question_replies', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['created_at'],
            },
        ),
    ]
