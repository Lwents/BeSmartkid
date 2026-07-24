from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Optional



@dataclass(frozen=True)
class Score:
    """Value object for assignment scores with validation."""
    
    points: Decimal
    max_points: Decimal
    
    def __post_init__(self):
        """Validate score constraints."""
        if self.points < 0:
            raise ValueError("Score cannot be negative")
        if self.max_points <= 0:
            raise ValueError("Max points must be positive")
        if self.points > self.max_points:
            raise ValueError("Score cannot exceed max points")
    
    @property
    def percentage(self) -> Decimal:
        """Calculate percentage score."""
        return (self.points / self.max_points * 100).quantize(Decimal('0.01'))
    
    def to_letter_grade(self) -> str:
        """Convert to letter grade (US system)."""
        pct = float(self.percentage)
        if pct >= 90: return 'A'
        if pct >= 80: return 'B'
        if pct >= 70: return 'C'
        if pct >= 60: return 'D'
        return 'F'
    
    def apply_penalty(self, penalty_pct: Decimal) -> 'Score':
        """Apply percentage penalty to score."""
        if penalty_pct < 0 or penalty_pct > 100:
            raise ValueError("Penalty must be between 0 and 100")
        
        reduction = self.points * (penalty_pct / 100)
        new_points = max(Decimal('0'), self.points - reduction)
        return Score(points=new_points, max_points=self.max_points)