# tests/support/mocks.py
"""Mock objects for testing."""
from unittest.mock import Mock
from uuid import UUID, uuid4
from typing import Optional, List

from assignments.domain.entities.assignment import Assignment
from assignments.domain.interfaces import IAssignmentRepository


class MockAssignmentRepository(IAssignmentRepository):
    """Mock repository for testing."""
    
    def __init__(self):
        self.assignments = {}
    
    def save(self, assignment: Assignment) -> Assignment:
        self.assignments[assignment.id] = assignment
        return assignment
    
    def get_by_id(self, assignment_id: UUID) -> Optional[Assignment]:
        return self.assignments.get(assignment_id)
    
    def list_by_classroom(self, classroom_id: UUID) -> List[Assignment]:
        return [
            a for a in self.assignments.values()
            if a.classroom_id == classroom_id
        ]
    
    def delete(self, assignment_id: UUID) -> bool:
        if assignment_id in self.assignments:
            del self.assignments[assignment_id]
            return True
        return False