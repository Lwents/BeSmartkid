# domain/interfaces.py
"""Repository interfaces for dependency inversion."""
from abc import ABC, abstractmethod
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from .entities.assignment import Assignment
from .entities.submission import Submission
from .entities.grade import Grade


class IAssignmentRepository(ABC):
    """Interface for assignment repository."""
    
    @abstractmethod
    def save(self, assignment: Assignment) -> Assignment:
        """Save assignment."""
        pass
    
    @abstractmethod
    def get_by_id(self, assignment_id: UUID) -> Optional[Assignment]:
        """Get assignment by ID."""
        pass
    
    @abstractmethod
    def list_by_classroom(self, classroom_id: UUID) -> List[Assignment]:
        """List assignments for classroom."""
        pass
    
    @abstractmethod
    def delete(self, assignment_id: UUID) -> bool:
        """Soft delete assignment."""
        pass


class ISubmissionRepository(ABC):
    """Interface for submission repository."""
    
    @abstractmethod
    def save(self, submission: Submission) -> Submission:
        """Save submission."""
        pass
    
    @abstractmethod
    def get_by_id(self, submission_id: UUID) -> Optional[Submission]:
        """Get submission by ID."""
        pass
    
    @abstractmethod
    def list_by_assignment(self, assignment_id: UUID) -> List[Submission]:
        """List submissions for assignment."""
        pass
    
    @abstractmethod
    def get_student_submission(self, assignment_id: UUID, student_id: UUID) -> Optional[Submission]:
        """Get student's submission for assignment."""
        pass


class IGradeRepository(ABC):
    """Interface for grade repository."""
    
    @abstractmethod
    def save(self, grade: Grade) -> Grade:
        """Save grade."""
        pass
    
    @abstractmethod
    def get_by_submission(self, submission_id: UUID) -> Optional[Grade]:
        """Get grade for submission."""
        pass