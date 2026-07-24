# tests/domain/test_entities.py
"""Tests for domain entities."""
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from assignments.domain.entities.assignment import Assignment
from assignments.domain.entities.submission import Submission
from assignments.domain.entities.grade import Grade
from assignments.domain.value_objects import (
    DueDate,
    LatePenalty,
    AssignmentType,
    Score,
    SubmissionStatus
)
from assignments.domain.exceptions import (
    AssignmentNotAvailable,
    SubmissionNotAllowed,
    LateSubmissionNotAllowed,
    InappropriateContent
)
from tests.support.test_utils import create_test_assignment


class TestAssignment:
    """Tests for Assignment entity."""
    
    def test_create_assignment(self):
        """Test creating assignment."""
        assignment = create_test_assignment()
        assert assignment.title == 'Test Assignment'
        assert assignment.status == 'draft'
    
    def test_inappropriate_content_raises_error(self):
        """Test inappropriate content detection."""
        with pytest.raises(InappropriateContent):
            create_test_assignment(
                title="This is inappropriate content"
            )
    
    def test_publish_assignment(self):
        """Test publishing assignment."""
        assignment = create_test_assignment()
        assignment.publish()
        assert assignment.status == 'published'
    
    def test_publish_already_published_raises_error(self):
        """Test publishing already published assignment."""
        assignment = create_test_assignment(status='published')
        with pytest.raises(ValueError):
            assignment.publish()
    
    def test_can_submit_when_published(self):
        """Test can submit when published."""
        now = datetime.utcnow()
        assignment = create_test_assignment(
            status='published',
            due_dates=DueDate(
                due_date=now + timedelta(days=7),
                available_from=now - timedelta(days=1),
                available_until=now + timedelta(days=14)
            )
        )
        assert assignment.can_submit(now, 1) is True
    
    def test_cannot_submit_when_draft(self):
        """Test cannot submit when draft."""
        now = datetime.utcnow()
        assignment = create_test_assignment(status='draft')
        assert assignment.can_submit(now, 1) is False
    
    def test_validate_submission_raises_when_not_available(self):
        """Test validation raises when not available."""
        now = datetime.utcnow()
        assignment = create_test_assignment(
            status='published',
            due_dates=DueDate(
                due_date=now + timedelta(days=7),
                available_from=now + timedelta(days=1),
                available_until=now + timedelta(days=14)
            )
        )
        with pytest.raises(AssignmentNotAvailable):
            assignment.validate_submission(now, 1)
    
    def test_validate_submission_raises_when_late_not_allowed(self):
        """Test validation raises when late not allowed."""
        now = datetime.utcnow()
        assignment = create_test_assignment(
            status='published',
            allow_late_submissions=False,
            due_dates=DueDate(
                due_date=now - timedelta(days=1),
                available_from=now - timedelta(days=10),
                available_until=now + timedelta(days=5)
            )
        )
        with pytest.raises(LateSubmissionNotAllowed):
            assignment.validate_submission(now, 1)
    
    def test_calculate_late_penalty(self):
        """Test late penalty calculation."""
        now = datetime.utcnow()
        assignment = create_test_assignment(
            due_dates=DueDate(
                due_date=now - timedelta(days=3),
                available_from=None,
                available_until=None
            ),
            late_penalty=LatePenalty(Decimal('10.00'))
        )
        penalty = assignment.calculate_late_penalty_for_submission(now)
        assert penalty == Decimal('30.00')


class TestSubmission:
    """Tests for Submission entity."""
    
    def test_create_submission(self):
        """Test creating submission."""
        submission = Submission(
            id=uuid4(),
            assignment_id=uuid4(),
            student_id=uuid4(),
            content="Test content"
        )
        assert submission.status == SubmissionStatus.DRAFT
    
    def test_submit_submission(self):
        """Test submitting submission."""
        submission = Submission(
            id=uuid4(),
            assignment_id=uuid4(),
            student_id=uuid4()
        )
        now = datetime.utcnow()
        submission.submit(now, (False, 0))
        assert submission.status == SubmissionStatus.SUBMITTED
        assert submission.submitted_at == now
        assert submission.is_late is False
    
    def test_submit_late_submission(self):
        """Test submitting late submission."""
        submission = Submission(
            id=uuid4(),
            assignment_id=uuid4(),
            student_id=uuid4()
        )
        now = datetime.utcnow()
        submission.submit(now, (True, 3))
        assert submission.is_late is True
        assert submission.late_days == 3
    
    def test_grade_submission(self):
        """Test grading submission."""
        submission = Submission(
            id=uuid4(),
            assignment_id=uuid4(),
            student_id=uuid4(),
            status=SubmissionStatus.SUBMITTED
        )
        
        score = Score(Decimal('85.00'), Decimal('100.00'))
        grade = Grade(
            id=uuid4(),
            submission_id=submission.id,
            grader_id=uuid4(),
            score=score
        )
        
        submission.grade(grade)
        assert submission.status == SubmissionStatus.GRADED


class TestGrade:
    """Tests for Grade entity."""
    
    def test_create_grade(self):
        """Test creating grade."""
        score = Score(Decimal('85.00'), Decimal('100.00'))
        grade = Grade(
            id=uuid4(),
            submission_id=uuid4(),
            grader_id=uuid4(),
            score=score
        )
        assert grade.raw_score == score
        assert grade.is_final is True
    
    def test_grade_with_late_penalty(self):
        """Test grade with late penalty."""
        score = Score(Decimal('100.00'), Decimal('100.00'))
        grade = Grade(
            id=uuid4(),
            submission_id=uuid4(),
            grader_id=uuid4(),
            score=score,
            late_penalty_applied=Decimal('20.00')
        )
        assert grade.raw_score.points == Decimal('100.00')
        assert grade.score.points == Decimal('80.00')