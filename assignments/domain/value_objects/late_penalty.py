from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Optional


@dataclass(frozen=True)
class LatePenalty:
    """Value object for late submission penalty calculation."""
    
    penalty_per_day: Decimal
    max_days: Optional[int] = None
    grace_period_hours: int = 0
    
    def __post_init__(self):
        """Validate penalty constraints."""
        if self.penalty_per_day < 0 or self.penalty_per_day > 100:
            raise ValueError("Penalty must be between 0 and 100 percent")
        if self.max_days is not None and self.max_days < 0:
            raise ValueError("Max days cannot be negative")
        if self.grace_period_hours < 0:
            raise ValueError("Grace period cannot be negative")
    
    def calculate_penalty(self, days_late: int, grace_minutes: int = 0) -> Decimal:
        """Calculate total penalty percentage."""
        if days_late <= 0:
            return Decimal('0')
        
        # Apply grace period
        if grace_minutes > 0 and days_late == 1:
            grace_hours = grace_minutes / 60
            if grace_hours <= self.grace_period_hours:
                return Decimal('0')
        
        # Cap at max days if specified
        effective_days = days_late
        if self.max_days is not None:
            effective_days = min(days_late, self.max_days)
        
        total_penalty = self.penalty_per_day * effective_days
        return min(Decimal('100'), total_penalty)