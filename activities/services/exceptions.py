class ServiceError(Exception):
    """Base service exception."""
    pass

class NotFoundError(ServiceError):
    pass

class ValidationError(ServiceError):
    pass

class PermissionDenied(ServiceError):
    pass