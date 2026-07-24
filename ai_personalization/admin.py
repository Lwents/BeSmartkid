from django.contrib import admin

# Register your models here.

# ai_personalization/admin.py
"""
Django admin configuration for personalization models.
"""
from django.contrib import admin
from django.utils.html import format_html
from .models import (
    LearningPath, Recommendation, LearningEvent,
    UserSkillMastery, ContentSkill, RecommendationLog,
    SkillPrerequisite, PersonalizationRule, MLModelVersion, UserProfile
)


@admin.register(LearningPath)
class LearningPathAdmin(admin.ModelAdmin):
    list_display = ['student', 'course', 'generated_at', 'ai_model', 'path_length']
    list_filter = ['ai_model', 'generated_at']
    search_fields = ['student__username', 'course__title']
    readonly_fields = ['generated_at']
    
    def path_length(self, obj):
        return len(obj.path)
    path_length.short_description = 'Path Length'


@admin.register(Recommendation)
class RecommendationAdmin(admin.ModelAdmin):
    list_display = ['student', 'recommended_lesson', 'score', 'generated_at']
    list_filter = ['generated_at']
    search_fields = ['student__username', 'recommended_lesson__title']
    ordering = ['-score', '-generated_at']


@admin.register(LearningEvent)
class LearningEventAdmin(admin.ModelAdmin):
    list_display = ['user', 'event_type', 'lesson', 'timestamp', 'success_indicator']
    list_filter = ['event_type', 'timestamp']
    search_fields = ['user__username', 'lesson__title']
    readonly_fields = ['timestamp']
    date_hierarchy = 'timestamp'
    
    def success_indicator(self, obj):
        if obj.is_successful:
            return format_html('<span style="color: green;">✓</span>')
        return format_html('<span style="color: red;">✗</span>')
    success_indicator.short_description = 'Success'


@admin.register(UserSkillMastery)
class UserSkillMasteryAdmin(admin.ModelAdmin):
    list_display = ['user', 'skill', 'mastery_bar', 'mastery', 'practice_count', 'last_update']
    list_filter = ['last_update']
    search_fields = ['user__username', 'skill']
    readonly_fields = ['last_update']
    
    def mastery_bar(self, obj):
        percentage = int(obj.mastery * 100)
        color = 'green' if percentage >= 70 else 'orange' if percentage >= 40 else 'red'
        return format_html(
            '<div style="width:100px; background-color:#f0f0f0;">'
            '<div style="width:{}px; background-color:{}; height:20px;"></div>'
            '</div>',
            percentage, color
        )
    mastery_bar.short_description = 'Mastery'


@admin.register(ContentSkill)
class ContentSkillAdmin(admin.ModelAdmin):
    list_display = ['lesson', 'skill', 'weight']
    list_filter = ['skill']
    search_fields = ['lesson__title', 'skill']


@admin.register(RecommendationLog)
class RecommendationLogAdmin(admin.ModelAdmin):
    list_display = ['user', 'lesson', 'score', 'source', 'shown_at', 'accepted']
    list_filter = ['source', 'accepted', 'shown_at']
    search_fields = ['user__username', 'lesson__title']
    readonly_fields = ['shown_at']


@admin.register(SkillPrerequisite)
class SkillPrerequisiteAdmin(admin.ModelAdmin):
    list_display = ['skill', 'prerequisite_skill', 'strength']
    search_fields = ['skill', 'prerequisite_skill']


@admin.register(PersonalizationRule)
class PersonalizationRuleAdmin(admin.ModelAdmin):
    list_display = ['name', 'priority', 'is_active', 'created_at']
    list_filter = ['is_active', 'priority']
    search_fields = ['name', 'description']


@admin.register(MLModelVersion)
class MLModelVersionAdmin(admin.ModelAdmin):
    list_display = ['name', 'version', 'model_type', 'is_active', 'deployed_at']
    list_filter = ['model_type', 'is_active']
    search_fields = ['name', 'version']


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'age_group', 'learning_style', 'difficulty_preference']
    list_filter = ['age_group', 'learning_style', 'difficulty_preference']
    search_fields = ['user__username']
