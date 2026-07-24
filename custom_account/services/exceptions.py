class DomainError(Exception):
    """Domain-specific error"""
    pass

class UserNotFoundError(Exception):
    pass

class IncorrectPasswordError(Exception):
    pass