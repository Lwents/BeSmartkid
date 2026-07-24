# Generated manually for LessonQuestionReport
from django.db import migrations, models
import uuid
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0007_lessonquestionreaction'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='LessonQuestionReport',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('reason', models.CharField(blank=True, max_length=255)),
                ('detail', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('question', models.ForeignKey(blank=True, null=True, on_delete=models.deletion.CASCADE, related_name='reports', to='activities.lessonquestion')),
                ('reply', models.ForeignKey(blank=True, null=True, on_delete=models.deletion.CASCADE, related_name='reports', to='activities.lessonquestionreply')),
                ('reporter', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='lesson_question_reports', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
