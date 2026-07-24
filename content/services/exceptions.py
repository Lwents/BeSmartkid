class DomainValidationError(ValueError):
    pass

class DomainNotFoundError(Exception):
    pass

# Alias for backward compatibility
NotFoundError = DomainNotFoundError

class InvalidOperation(Exception):
    pass