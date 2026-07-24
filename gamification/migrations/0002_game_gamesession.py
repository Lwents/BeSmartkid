# Generated manually for Game and GameSession models

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('gamification', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Game',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('title', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True)),
                ('game_type', models.CharField(choices=[('quiz', 'Trắc nghiệm nhanh'), ('word_match', 'Ghép từ'), ('puzzle', 'Đố vui'), ('memory', 'Trí nhớ'), ('fill_blank', 'Điền từ')], default='quiz', max_length=32)),
                ('difficulty', models.CharField(choices=[('easy', 'Dễ'), ('medium', 'Trung bình'), ('hard', 'Khó')], default='easy', max_length=16)),
                ('questions', models.JSONField(default=list)),
                ('settings', models.JSONField(default=dict)),
                ('subject', models.CharField(blank=True, max_length=64)),
                ('grade_level', models.PositiveIntegerField(blank=True, null=True)),
                ('is_published', models.BooleanField(default=False)),
                ('play_count', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_games', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Game',
                'verbose_name_plural': 'Games',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='GameSession',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('score', models.PositiveIntegerField(default=0)),
                ('max_score', models.PositiveIntegerField(default=0)),
                ('time_spent', models.PositiveIntegerField(default=0)),
                ('completed', models.BooleanField(default=False)),
                ('answers', models.JSONField(default=list)),
                ('started_at', models.DateTimeField(auto_now_add=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('game', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sessions', to='gamification.game')),
                ('player', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='game_sessions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Game Session',
                'verbose_name_plural': 'Game Sessions',
                'ordering': ['-started_at'],
            },
        ),
    ]
