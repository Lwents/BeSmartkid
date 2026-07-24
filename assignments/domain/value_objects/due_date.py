from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Optional



@dataclass(frozen=True)
class DueDate:
    """Value object representing assignment due date with validation."""
    
    due_date: Optional[datetime]
    available_from: Optional[datetime]
    available_until: Optional[datetime]
    
    def __post_init__(self):
        """Validate date constraints."""
        if self.available_from and self.available_until:
            if self.available_from >= self.available_until:
                raise ValueError("available_from must be before available_until")
        
        if self.due_date and self.available_until:
            if self.due_date > self.available_until:
                raise ValueError("due_date must be before available_until")
    
    def is_available(self, current_time: datetime) -> bool:
        """Check if assignment is currently available."""
        if self.available_from and current_time < self.available_from:
            return False
        if self.available_until and current_time > self.available_until:
            return False
        return True
    
    def is_past_due(self, current_time: datetime) -> bool:
        """Check if assignment is past due."""
        return self.due_date is not None and current_time > self.due_date
    
    def days_late(self, submission_time: datetime) -> int:
        """Calculate how many days late a submission is."""
        if not self.due_date or submission_time <= self.due_date:
            return 0
        delta = submission_time - self.due_date
        return max(1, delta.days + (1 if delta.seconds > 0 else 0))