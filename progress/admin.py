from django.contrib import admin
from .models import UserProgress, UserLessonProgress

@admin.register(UserProgress)
class UserProgressAdmin(admin.ModelAdmin):
    list_display = ('user', 'course', 'progress_percentage', 'completed_at')
    list_filter = ('course',)
    search_fields = ('user__username', 'user__email')

@admin.register(UserLessonProgress)
class UserLessonProgressAdmin(admin.ModelAdmin):
    list_display = ('user_progress', 'lesson', 'status', 'completed_at')
    list_filter = ('status',)
    search_fields = ('user_progress__user__username', 'lesson__title')