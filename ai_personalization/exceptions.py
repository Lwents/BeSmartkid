# ai_personalization/exceptions.py
"""
Custom exceptions for personalization module.
"""


class PersonalizationError(Exception):
    """Base exception for personalization errors."""
    pass


class InsufficientDataError(PersonalizationError):
    """Raised when insufficient data for personalization."""
    pass


class ModelNotTrainedError(PersonalizationError):
    """Raised when ML model is not trained."""
    pass


class PrerequisiteNotMetError(PersonalizationError):
    """Raised when skill prerequisites are not satisfied."""
    pass