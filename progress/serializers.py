
from rest_framework import serializers
from .models import UserProgress, UserLessonProgress

class UserLessonProgressSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserLessonProgress
        fields = ('id', 'lesson', 'status', 'started_at', 'completed_at')

class UserProgressSerializer(serializers.ModelSerializer):
    lesson_progress = UserLessonProgressSerializer(many=True, read_only=True)

    class Meta:
        model = UserProgress
        fields = ('id', 'course', 'progress_percentage', 'completed_lessons', 'total_lessons', 'started_at', 'completed_at', 'lesson_progress')
