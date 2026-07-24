# ai_personalization/serializers.py

from rest_framework import serializers
from ai_personalization.models import (LearningEvent, RecommendationLog, LearningPath, Recommendation,
                                       UserSkillMastery, ContentSkill, SkillPrerequisite, 
                                       PersonalizationRule, UserProfile, MLModelVersion)



class LearningPathSerializer(serializers.ModelSerializer):
    """Serializer for learning paths with nested lesson details."""
    
    student_username = serializers.CharField(source='student.username', read_only=True)
    course_title = serializers.CharField(source='course.title', read_only=True)
    next_lesson = serializers.SerializerMethodField()
    progress_percentage = serializers.SerializerMethodField()
    
    class Meta:
        model = LearningPath
        fields = [
            'id', 'student', 'student_username', 'course', 'course_title',
            'path', 'generated_at', 'ai_model', 'metadata',
            'next_lesson', 'progress_percentage'
        ]
        read_only_fields = ['id', 'generated_at']
    
    def get_next_lesson(self, obj):
        """Get next unvisited lesson."""
        return obj.get_next_lesson()
    
    def get_progress_percentage(self, obj):
        """Calculate completion percentage of path."""
        if not obj.path:
            return 0.0
        
        # Count completed lessons (this would query LearningEvent in real implementation)
        completed = 0  # Placeholder
        total = len(obj.path)
        return (completed / total * 100) if total > 0 else 0.0


class RecommendationSerializer(serializers.ModelSerializer):
    """Serializer for lesson recommendations."""
    
    student_username = serializers.CharField(source='student.username', read_only=True)
    lesson_title = serializers.CharField(source='recommended_lesson.title', read_only=True)
    lesson_difficulty = serializers.CharField(source='recommended_lesson.difficulty', read_only=True)
    
    class Meta:
        model = Recommendation
        fields = [
            'id', 'student', 'student_username', 'recommended_lesson',
            'lesson_title', 'lesson_difficulty', 'score', 'reason', 'generated_at'
        ]
        read_only_fields = ['id', 'generated_at']
    
    def validate_score(self, value):
        """Ensure score is between 0 and 1."""
        if not 0 <= value <= 1:
            raise serializers.ValidationError("Score must be between 0 and 1")
        return value


class LearningEventSerializer(serializers.ModelSerializer):
    """Serializer for learning events (write-heavy, minimal validation)."""
    
    user_username = serializers.CharField(source='user.username', read_only=True)
    course_title = serializers.CharField(source='course.title', read_only=True)
    lesson_title = serializers.CharField(source='lesson.title', read_only=True)
    
    class Meta:
        model = LearningEvent
        fields = [
            'id', 'user', 'user_username', 'course', 'course_title',
            'lesson', 'lesson_title', 'timestamp', 'event_type',
            'detail', 'session_id'
        ]
        read_only_fields = ['id', 'timestamp']
    
    def validate_event_type(self, value):
        """Validate event type is one of allowed choices."""
        allowed = ['start', 'submit', 'hint', 'skip', 'complete', 'pause', 'resume']
        if value not in allowed:
            raise serializers.ValidationError(f"Event type must be one of: {', '.join(allowed)}")
        return value
    
    def validate_detail(self, value):
        """Validate detail structure based on event type."""
        if not isinstance(value, dict):
            raise serializers.ValidationError("Detail must be a dictionary")
        return value


class ContentSkillSerializer(serializers.ModelSerializer):
    """Serializer for content-skill mappings."""
    
    lesson_title = serializers.CharField(source='lesson.title', read_only=True)
    
    class Meta:
        model = ContentSkill
        fields = ['id', 'lesson', 'lesson_title', 'skill', 'weight']
        read_only_fields = ['id']
    
    def validate_weight(self, value):
        """Ensure weight is between 0 and 1."""
        if not 0 <= value <= 1:
            raise serializers.ValidationError("Weight must be between 0 and 1")
        return value


class UserSkillMasterySerializer(serializers.ModelSerializer):
    """Serializer for skill mastery with computed fields."""
    
    user_username = serializers.CharField(source='user.username', read_only=True)
    recall_probability = serializers.SerializerMethodField()
    success_rate = serializers.SerializerMethodField()
    mastery_level = serializers.SerializerMethodField()
    
    class Meta:
        model = UserSkillMastery
        fields = [
            'user', 'user_username', 'skill', 'mastery', 'last_update',
            'half_life_days', 'practice_count', 'correct_count',
            'recall_probability', 'success_rate', 'mastery_level'
        ]
        read_only_fields = ['last_update', 'practice_count', 'correct_count']
    
    def get_recall_probability(self, obj):
        """Current recall probability using HLR."""
        return round(obj.calculate_recall_probability(), 3)
    
    def get_success_rate(self, obj):
        """Historical success rate."""
        if obj.practice_count == 0:
            return None
        return round(obj.correct_count / obj.practice_count, 3)
    
    def get_mastery_level(self, obj):
        """Human-readable mastery level."""
        if obj.mastery >= 0.9:
            return 'Mastered'
        elif obj.mastery >= 0.7:
            return 'Proficient'
        elif obj.mastery >= 0.5:
            return 'Familiar'
        elif obj.mastery >= 0.3:
            return 'Learning'
        else:
            return 'Beginner'


class RecommendationLogSerializer(serializers.ModelSerializer):
    """Serializer for recommendation audit logs."""
    
    user_username = serializers.CharField(source='user.username', read_only=True)
    lesson_title = serializers.CharField(source='lesson.title', read_only=True)
    acceptance_rate = serializers.SerializerMethodField()
    
    class Meta:
        model = RecommendationLog
        fields = [
            'id', 'user', 'user_username', 'lesson', 'lesson_title',
            'score', 'reason', 'source', 'shown_at', 'acted_at',
            'accepted', 'feedback', 'acceptance_rate'
        ]
        read_only_fields = ['id', 'shown_at']
    
    def get_acceptance_rate(self, obj):
        """Calculate acceptance rate for this recommendation source."""
        # This would be computed from aggregate query in real implementation
        return None


class SkillPrerequisiteSerializer(serializers.ModelSerializer):
    """Serializer for skill dependency graph."""
    
    class Meta:
        model = SkillPrerequisite
        fields = ['id', 'skill', 'prerequisite_skill', 'strength']
        read_only_fields = ['id']
    
    def validate(self, data):
        """Prevent circular dependencies."""
        if data.get('skill') == data.get('prerequisite_skill'):
            raise serializers.ValidationError("A skill cannot be its own prerequisite")
        return data


class PersonalizationRuleSerializer(serializers.ModelSerializer):
    """Serializer for rule-based personalization."""
    
    class Meta:
        model = PersonalizationRule
        fields = [
            'id', 'name', 'description', 'condition', 'action',
            'priority', 'is_active', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']
    
    def validate_condition(self, value):
        """Validate condition is valid JSON."""
        if not isinstance(value, dict):
            raise serializers.ValidationError("Condition must be a dictionary")
        return value
    
    def validate_action(self, value):
        """Validate action is valid JSON."""
        if not isinstance(value, dict):
            raise serializers.ValidationError("Action must be a dictionary")
        return value


class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer for user learning profiles."""
    
    user_username = serializers.CharField(source='user.username', read_only=True)
    
    class Meta:
        model = UserProfile
        fields = [
            'user', 'user_username', 'age_group', 'learning_style',
            'difficulty_preference', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class MLModelVersionSerializer(serializers.ModelSerializer):
    """Serializer for ML model versioning."""
    
    class Meta:
        model = MLModelVersion
        fields = [
            'id', 'name', 'version', 'model_type', 'parameters',
            'metrics', 'is_active', 'deployed_at', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


# Specialized serializers for specific use cases

class MasteryDashboardSerializer(serializers.Serializer):
    """Aggregate mastery statistics for dashboard."""
    
    total_skills = serializers.IntegerField()
    mastered_skills = serializers.IntegerField()
    proficient_skills = serializers.IntegerField()
    learning_skills = serializers.IntegerField()
    beginner_skills = serializers.IntegerField(required=False)
    weak_skills = serializers.ListField(child=serializers.CharField())
    average_mastery = serializers.FloatField()
    skills_needing_practice = UserSkillMasterySerializer(many=True)


class PathGenerationRequestSerializer(serializers.Serializer):
    """Request serializer for path generation."""
    
    course_id = serializers.UUIDField()
    preferences = serializers.DictField(required=False, default=dict)
    focus_areas = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list
    )
    difficulty_target = serializers.ChoiceField(
        choices=['easy', 'medium', 'hard', 'adaptive'],
        default='adaptive'
    )


class RecommendationRequestSerializer(serializers.Serializer):
    """Request serializer for recommendations."""
    
    limit = serializers.IntegerField(default=5, min_value=1, max_value=20)
    exclude_completed = serializers.BooleanField(default=True)
    include_reasoning = serializers.BooleanField(default=True)
    algorithm = serializers.ChoiceField(
        choices=['hybrid', 'collaborative', 'content_based', 'rule_based'],
        default='hybrid'
    )


class EventStatisticsSerializer(serializers.Serializer):
    """Serializer for event statistics response."""
    
    total_events = serializers.IntegerField()
    by_type = serializers.ListField(child=serializers.DictField())
    success_rate = serializers.FloatField()
    date_range = serializers.DictField()


class SkillNeedsPracticeSerializer(serializers.Serializer):
    """Serializer for skills needing practice."""
    
    skill = serializers.CharField()
    mastery = serializers.FloatField()
    recall_probability = serializers.FloatField()
    days_since_practice = serializers.IntegerField()
    half_life_days = serializers.FloatField()
    urgency = serializers.ChoiceField(choices=['low', 'medium', 'high'])


class SkillCategorySerializer(serializers.Serializer):
    """Serializer for skill categories grouping."""
    
    category = serializers.CharField()
    skills = serializers.ListField(child=serializers.DictField())
    average_mastery = serializers.FloatField()
    total_skills = serializers.IntegerField()


class AnalyticsResponseSerializer(serializers.Serializer):
    """Serializer for system analytics response."""
    
    recommendation_metrics = serializers.DictField()
    mastery_metrics = serializers.DictField()
    activity_metrics = serializers.DictField()
    timestamp = serializers.DateTimeField()


class SkillGraphNodeSerializer(serializers.Serializer):
    """Serializer for skill graph nodes."""
    
    skill = serializers.CharField()
    prerequisites = serializers.ListField(child=serializers.DictField())
    dependents = serializers.ListField(child=serializers.DictField())
    ready = serializers.BooleanField(required=False)


class PathProgressSerializer(serializers.Serializer):
    """Serializer for learning path progress."""
    
    total_lessons = serializers.IntegerField()
    completed = serializers.IntegerField()
    remaining = serializers.IntegerField()
    progress_percentage = serializers.FloatField()
