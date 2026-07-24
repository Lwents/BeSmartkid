"""DRF Serializers for Assignment API."""
from rest_framework import serializers
from decimal import Decimal
from datetime import datetime

from assignments.application.dto.assignment_dto import (
    CreateAssignmentDTO,
    SubmitAssignmentDTO,
    GradeSubmissionDTO
)


class AssignmentCreateSerializer(serializers.Serializer):
    """Serializer for creating assignments."""
    
    title = serializers.CharField(max_length=255)
    description = serializers.CharField(allow_blank=True)
    assignment_type = serializers.ChoiceField(
        choices=['homework', 'quiz', 'project', 'worksheet', 'essay']
    )
    max_score = serializers.DecimalField(max_digits=6, decimal_places=2, min_value=0.01)
    due_date = serializers.DateTimeField(required=False, allow_null=True)
    available_from = serializers.DateTimeField(required=False, allow_null=True)
    available_until = serializers.DateTimeField(required=False, allow_null=True)
    classroom_id = serializers.UUIDField(required=False, allow_null=True)
    allow_late_submissions = serializers.BooleanField(default=True)
    late_penalty_percent = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        min_value=Decimal('0.00'),
        max_value=Decimal('100.00')
    )
    max_attempts = serializers.IntegerField(default=1, min_value=0)
    is_group_assignment = serializers.BooleanField(default=False)
    requires_parent_consent = serializers.BooleanField(default=False)
    age_appropriate_level = serializers.IntegerField(default=1, min_value=1, max_value=5)
    auto_grade = serializers.BooleanField(default=False)
    
    def validate(self, data):
        """Validate date constraints."""
        if data.get('available_from') and data.get('available_until'):
            if data['available_from'] >= data['available_until']:
                raise serializers.ValidationError(
                    "available_from must be before available_until"
                )
        
        if data.get('due_date') and data.get('available_until'):
            if data['due_date'] > data['available_until']:
                raise serializers.ValidationError(
                    "due_date must be before available_until"
                )
        
        return data
    
    def to_dto(self, teacher_id):
        """Convert to DTO."""
        return CreateAssignmentDTO(
            teacher_id=teacher_id,
            **self.validated_data
        )


class AssignmentResponseSerializer(serializers.Serializer):
    """Serializer for assignment responses."""
    
    id = serializers.UUIDField(read_only=True)
    title = serializers.CharField()
    description = serializers.CharField()
    assignment_type = serializers.CharField()
    max_score = serializers.DecimalField(max_digits=6, decimal_places=2)
    status = serializers.CharField()
    due_date = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()
    teacher_id = serializers.UUIDField(allow_null=True)
    classroom_id = serializers.UUIDField(allow_null=True)


class SubmissionCreateSerializer(serializers.Serializer):
    """Serializer for creating submissions."""
    
    content = serializers.CharField(required=False, allow_blank=True)
    
    def to_dto(self, assignment_id, student_id):
        """Convert to DTO."""
        return SubmitAssignmentDTO(
            assignment_id=assignment_id,
            student_id=student_id,
            content=self.validated_data.get('content', ''),
            submission_time=datetime.utcnow()
        )


class GradeSubmissionSerializer(serializers.Serializer):
    """Serializer for grading submissions."""
    
    score = serializers.DecimalField(max_digits=6, decimal_places=2, min_value=0)
    max_score = serializers.DecimalField(max_digits=6, decimal_places=2, min_value=0.01)
    feedback = serializers.CharField(required=False, allow_blank=True)
    
    def validate(self, data):
        """Validate score constraints."""
        if data['score'] > data['max_score']:
            raise serializers.ValidationError("Score cannot exceed max_score")
        return data
    
    def to_dto(self, submission_id, grader_id):
        """Convert to DTO."""
        return GradeSubmissionDTO(
            submission_id=submission_id,
            grader_id=grader_id,
            score=self.validated_data['score'],
            max_score=self.validated_data['max_score'],
            feedback=self.validated_data.get('feedback', '')
        )