# tests/domain/test_value_objects.py
"""Tests for value objects."""
import pytest
from datetime import datetime, timedelta
from decimal import Decimal

from assignments.domain.value_objects import (
    DueDate,
    Score,
    LatePenalty,
    SubmissionStatus
)


class TestDueDate:
    """Tests for DueDate value object."""
    
    def test_valid_due_date(self):
        """Test creating valid due date."""
        now = datetime.utcnow()
        due_date = DueDate(
            due_date=now + timedelta(days=7),
            available_from=now,
            available_until=now + timedelta(days=14)
        )
        assert due_date.due_date is not None
    
    def test_invalid_date_range(self):
        """Test invalid date range raises error."""
        now = datetime.utcnow()
        with pytest.raises(ValueError, match="available_from must be before"):
            DueDate(
                due_date=now + timedelta(days=7),
                available_from=now + timedelta(days=10),
                available_until=now + timedelta(days=5)
            )
    
    def test_is_available(self):
        """Test availability check."""
        now = datetime.utcnow()
        due_date = DueDate(
            due_date=now + timedelta(days=7),
            available_from=now - timedelta(days=1),
            available_until=now + timedelta(days=14)
        )
        assert due_date.is_available(now) is True

    def test_days_late(self):
        """Test late days calculation."""
        now = datetime.utcnow()
        due_date = DueDate(
            due_date=now - timedelta(days=3),
            available_from=None,
            available_until=None
        )
        submission_time = now
        assert due_date.days_late(submission_time) == 3

class TestScore:
    """Tests for Score value object."""
    
    def test_valid_score(self):
        """Test creating valid score."""
        score = Score(points=Decimal('85.00'), max_points=Decimal('100.00'))
        assert score.points == Decimal('85.00')
        assert score.max_points == Decimal('100.00')
    
    def test_negative_score_raises_error(self):
        """Test negative score raises error."""
        with pytest.raises(ValueError, match="Score cannot be negative"):
            Score(points=Decimal('-10.00'), max_points=Decimal('100.00'))
    
    def test_score_exceeds_max_raises_error(self):
        """Test score exceeding max raises error."""
        with pytest.raises(ValueError, match="Score cannot exceed max points"):
            Score(points=Decimal('110.00'), max_points=Decimal('100.00'))
    
    def test_percentage_calculation(self):
        """Test percentage calculation."""
        score = Score(points=Decimal('85.00'), max_points=Decimal('100.00'))
        assert score.percentage == Decimal('85.00')
    
    def test_letter_grade_conversion(self):
        """Test letter grade conversion."""
        assert Score(Decimal('95'), Decimal('100')).to_letter_grade() == 'A'
        assert Score(Decimal('85'), Decimal('100')).to_letter_grade() == 'B'
        assert Score(Decimal('75'), Decimal('100')).to_letter_grade() == 'C'
        assert Score(Decimal('65'), Decimal('100')).to_letter_grade() == 'D'
        assert Score(Decimal('50'), Decimal('100')).to_letter_grade() == 'F'
    
    def test_apply_penalty(self):
        """Test applying penalty to score."""
        score = Score(points=Decimal('100.00'), max_points=Decimal('100.00'))
        penalized = score.apply_penalty(Decimal('10.00'))
        assert penalized.points == Decimal('90.00')


class TestLatePenalty:
    """Tests for LatePenalty value object."""
    
    def test_valid_penalty(self):
        """Test creating valid penalty."""
        penalty = LatePenalty(penalty_per_day=Decimal('10.00'))
        assert penalty.penalty_per_day == Decimal('10.00')
    
    def test_invalid_penalty_raises_error(self):
        """Test invalid penalty raises error."""
        with pytest.raises(ValueError):
            LatePenalty(penalty_per_day=Decimal('150.00'))
    
    def test_calculate_penalty(self):
        """Test penalty calculation."""
        penalty = LatePenalty(penalty_per_day=Decimal('10.00'))
        assert penalty.calculate_penalty(3) == Decimal('30.00')
    
    def test_penalty_with_max_days(self):
        """Test penalty with max days cap."""
        penalty = LatePenalty(penalty_per_day=Decimal('10.00'), max_days=5)
        assert penalty.calculate_penalty(10) == Decimal('50.00')
    
    def test_penalty_capped_at_100(self):
        """Test penalty is capped at 100%."""
        penalty = LatePenalty(penalty_per_day=Decimal('30.00'))
        assert penalty.calculate_penalty(5) == Decimal('100.00')