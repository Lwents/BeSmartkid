# infrastructure/repositories/assignment_repository.py
"""Repository implementation for Assignment."""
from typing import List, Optional
from uuid import UUID

from ...domain.entities.assignment import Assignment
from ...domain.value_objects import DueDate, LatePenalty, AssignmentType
from ...domain.interfaces import IAssignmentRepository
from assignments.models import Assignment


class AssignmentRepository(IAssignmentRepository):
    """Django ORM implementation of assignment repository."""
    
    def save(self, assignment: Assignment) -> Assignment:
        """Save assignment to database."""
        model, created = Assignment.objects.update_or_create(
            id=assignment.id,
            defaults={
                'title': assignment.title,
                'description': assignment.description,
                'assignment_type': assignment.assignment_type.value,
                'status': assignment.status,
                'max_score': assignment.max_score,
                'due_date': assignment.due_dates.due_date,
                'available_from': assignment.due_dates.available_from,
                'available_until': assignment.due_dates.available_until,
                'allow_late_submissions': assignment.allow_late_submissions,
                'late_penalty_percent': assignment.late_penalty.penalty_per_day,
                'max_attempts': assignment.max_attempts,
                'is_group_assignment': assignment.is_group_assignment,
                'requires_parent_consent': assignment.requires_parent_consent,
                'age_appropriate_level': assignment.age_appropriate_level,
                'auto_grade': assignment.auto_grade,
                'teacher_id': assignment.teacher_id,
                'classroom_id': assignment.classroom_id,
                'version': assignment.version + 1 if not created else 1
            }
        )
        return self._to_entity(model)
    
    def get_by_id(self, assignment_id: UUID) -> Optional[Assignment]:
        """Get assignment by ID."""
        try:
            model = Assignment.objects.get(id=assignment_id, deleted_at__isnull=True)
            return self._to_entity(model)
        except Assignment.DoesNotExist:
            return None
    
    def list_by_classroom(self, classroom_id: UUID) -> List[Assignment]:
        """List assignments for classroom."""
        models = Assignment.objects.filter(
            classroom_id=classroom_id,
            deleted_at__isnull=True
        ).order_by('-created_at')
        return [self._to_entity(m) for m in models]
    
    def delete(self, assignment_id: UUID) -> bool:
        """Soft delete assignment."""
        from django.utils import timezone
        count = Assignment.objects.filter(
            id=assignment_id,
            deleted_at__isnull=True
        ).update(deleted_at=timezone.now())
        return count > 0
    
    def _to_entity(self, model: Assignment) -> Assignment:
        """Convert ORM model to domain entity."""
        due_dates = DueDate(
            due_date=model.due_date,
            available_from=model.available_from,
            available_until=model.available_until
        )
        
        late_penalty = LatePenalty(
            penalty_per_day=model.late_penalty_percent,
            max_days=None
        )
        
        return Assignment(
            id=model.id,
            title=model.title,
            description=model.description,
            assignment_type=AssignmentType(model.assignment_type),
            max_score=model.max_score,
            due_dates=due_dates,
            late_penalty=late_penalty,
            max_attempts=model.max_attempts,
            allow_late_submissions=model.allow_late_submissions,
            is_group_assignment=model.is_group_assignment,
            requires_parent_consent=model.requires_parent_consent,
            age_appropriate_level=model.age_appropriate_level,
            auto_grade=model.auto_grade,
            teacher_id=model.teacher_id,
            classroom_id=model.classroom_id,
            created_at=model.created_at,
            status=model.status
        )