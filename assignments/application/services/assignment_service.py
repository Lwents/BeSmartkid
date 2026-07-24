# application/services/assignment_service.py
"""Assignment service for use cases."""
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID, uuid4

from ..dto.assignment_dto import CreateAssignmentDTO, AssignmentResponseDTO
from ...domain.entities.assignment import Assignment
from ...domain.value_objects import DueDate, LatePenalty, AssignmentType
from ...domain.interfaces import IAssignmentRepository
from ...domain.exceptions import AssignmentNotFound



class AssignmentService:
    """
    Application service for assignment use cases.
    
    Orchestrates domain logic and repository operations.
    Framework-agnostic business logic.
    """
    
    def __init__(self, repository: IAssignmentRepository):
        self.repository = repository
    
    def create_assignment(self, dto: CreateAssignmentDTO) -> AssignmentResponseDTO:
        """
        Create new assignment.
        
        Args:
            dto: Assignment creation data
            
        Returns:
            Created assignment DTO
        """
        # Create value objects
        due_dates = DueDate(
            due_date=dto.due_date,
            available_from=dto.available_from,
            available_until=dto.available_until
        )
        
        late_penalty = LatePenalty(
            penalty_per_day=dto.late_penalty_percent,
            max_days=None
        )
        
        # Create entity
        assignment = Assignment(
            id=uuid4(),
            title=dto.title,
            description=dto.description,
            assignment_type=AssignmentType(dto.assignment_type),
            max_score=dto.max_score,
            due_dates=due_dates,
            late_penalty=late_penalty,
            max_attempts=dto.max_attempts,
            allow_late_submissions=dto.allow_late_submissions,
            is_group_assignment=dto.is_group_assignment,
            requires_parent_consent=dto.requires_parent_consent,
            age_appropriate_level=dto.age_appropriate_level,
            auto_grade=dto.auto_grade,
            teacher_id=dto.teacher_id,
            classroom_id=dto.classroom_id,
            status='draft'
        )
        
        # Persist
        saved = self.repository.save(assignment)
        
        # Return DTO
        return self._to_response_dto(saved)
    
    def publish_assignment(self, assignment_id: UUID) -> AssignmentResponseDTO:
        """Publish assignment to students."""
        assignment = self.repository.get_by_id(assignment_id)
        if not assignment:
            raise AssignmentNotFound(f"Assignment {assignment_id} not found")
        
        assignment.publish()
        saved = self.repository.save(assignment)
        return self._to_response_dto(saved)
    
    def get_assignment(self, assignment_id: UUID) -> AssignmentResponseDTO:
        """Get assignment by ID."""
        assignment = self.repository.get_by_id(assignment_id)
        if not assignment:
            raise AssignmentNotFound(f"Assignment {assignment_id} not found")
        return self._to_response_dto(assignment)
    
    def list_classroom_assignments(self, classroom_id: UUID) -> List[AssignmentResponseDTO]:
        """List all assignments for classroom."""
        assignments = self.repository.list_by_classroom(classroom_id)
        return [self._to_response_dto(a) for a in assignments]
    
    def _to_response_dto(self, assignment: Assignment) -> AssignmentResponseDTO:
        """Convert entity to response DTO."""
        return AssignmentResponseDTO(
            id=assignment.id,
            title=assignment.title,
            description=assignment.description,
            assignment_type=assignment.assignment_type.value,
            max_score=assignment.max_score,
            status=assignment.status,
            due_date=assignment.due_dates.due_date,
            created_at=assignment.created_at,
            teacher_id=assignment.teacher_id,
            classroom_id=assignment.classroom_id
        )