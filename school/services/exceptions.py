class ServiceError(Exception):
    pass

class ConflictError(ServiceError):
    pass

class NotFoundError(ServiceError):
    pass

class PermissionDenied(ServiceError):
    pass

class InvalidOperation(ServiceError):
    pass

class DomainValidationError(ValueError):
    """Validation error specific to domain rules."""
    pass

class DuplicateError(Exception):
    """Duplicate / uniqueness violation in domain."""
    pass