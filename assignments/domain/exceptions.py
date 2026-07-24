class AssignmentDomainException(Exception):
    """Base exception for assignment domain errors."""
    pass


class AssignmentNotFound(AssignmentDomainException):
    """Raised when assignment cannot be found."""
    pass


class AssignmentNotAvailable(AssignmentDomainException):
    """Raised when assignment is not yet available or expired."""
    pass


class SubmissionNotAllowed(AssignmentDomainException):
    """Raised when submission is not allowed."""
    pass


class LateSubmissionNotAllowed(AssignmentDomainException):
    """Raised when late submission is disabled."""
    pass


class SubmissionLimitExceeded(AssignmentDomainException):
    """Raised when max attempts exceeded."""
    pass


class InvalidGrade(AssignmentDomainException):
    """Raised when grade is invalid."""
    pass


class PermissionDenied(AssignmentDomainException):
    """Raised when user lacks permission."""
    pass


class InappropriateContent(AssignmentDomainException):
    """Raised when content is inappropriate for age level."""
    pass