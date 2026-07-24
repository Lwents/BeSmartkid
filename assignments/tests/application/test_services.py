# tests/application/test_services.py
"""Tests for application services."""
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from assignments.application.services.assignment_service import AssignmentService
from assignments.application.services.submission_service import SubmissionService
from assignments.application.services.grading_service import GradingService
from assignments.application.dto.assignment_dto import (
    CreateAssignmentDTO,
    SubmitAssignmentDTO,
    GradeSubmissionDTO
)
from assignments.domain.exceptions import AssignmentNotFound
from tests.support.mocks import MockAssignmentRepository


class TestAssignmentService:
    """Tests for AssignmentService."""
    
    def test_create_assignment(self):
        """Test creating assignment."""
        repo = MockAssignmentRepository()
        service = AssignmentService(repo)
        
        dto = CreateAssignmentDTO(
            title="Test Assignment",
            description="Test Description",
            assignment_type="homework",
            max_score=Decimal('100.00'),
            due_date=datetime.utcnow() + timedelta(days=7),
            available_from=datetime.utcnow(),
            available_until=datetime.utcnow() + timedelta(days=14),
            teacher_id=uuid4(),
            classroom_id=uuid4()
        )
        
        result = service.create_assignment(dto)
        
        assert result.title == "Test Assignment"
        assert result.status == "draft"
        assert result.id is not None
    
    def test_publish_assignment(self):
        """Test publishing assignment."""
        repo = MockAssignmentRepository()
        service = AssignmentService(repo)
        
        # Create first
        dto = CreateAssignmentDTO(
            title="Test",
            description="Test",
            assignment_type="homework",
            max_score=Decimal('100.00'),
            due_date=None,
            available_from=None,
            available_until=None,
            teacher_id=uuid4()
        )
        created = service.create_assignment(dto)
        
        # Then publish
        result = service.publish_assignment(created.id)
        assert result.status == "published"
    
    def test_get_assignment_not_found(self):
        """Test get assignment that doesn't exist."""
        repo = MockAssignmentRepository()
        service = AssignmentService(repo)
        
        with pytest.raises(AssignmentNotFound):
            service.get_assignment(uuid4())