"""Custom exceptions for Ascent Beacon API.

These exceptions provide structured error handling with:
- Clear error types for different failure modes
- HTTP status code mapping
- Structured error details for client responses

Usage:
    from app.core.exceptions import NotFoundError, ValidationError
    
    raise NotFoundError("User", user_id)
    raise ValidationError("Invalid email format", field="email")
"""

from typing import Any


class AscentBeaconError(Exception):
    """Base exception for all Ascent Beacon errors.
    
    Attributes:
        message: Human-readable error message
        status_code: HTTP status code to return
        error_code: Machine-readable error code
        details: Additional error context
    """
    
    message: str = "An error occurred"
    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"
    
    def __init__(
        self,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.__class__.message
        self.details = details or {}
        super().__init__(self.message)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert exception to API response format."""
        response: dict[str, Any] = {
            "error": self.error_code,
            "message": self.message,
        }
        if self.details:
            response["details"] = self.details
        return response


# 400 Bad Request
class ValidationError(AscentBeaconError):
    """Raised when input validation fails."""
    
    status_code = 400
    error_code = "VALIDATION_ERROR"
    message = "Validation failed"
    
    def __init__(
        self,
        message: str = "Validation failed",
        field: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        if field:
            details = details or {}
            details["field"] = field
        super().__init__(message, details)


class BadRequestError(AscentBeaconError):
    """Raised for malformed requests."""
    
    status_code = 400
    error_code = "BAD_REQUEST"
    message = "Bad request"


# 401 Unauthorized
class AuthenticationError(AscentBeaconError):
    """Raised when authentication fails."""
    
    status_code = 401
    error_code = "AUTHENTICATION_ERROR"
    message = "Authentication required"


class TokenExpiredError(AuthenticationError):
    """Raised when a token has expired."""
    
    error_code = "TOKEN_EXPIRED"
    message = "Token has expired"


class InvalidTokenError(AuthenticationError):
    """Raised when a token is invalid."""
    
    error_code = "INVALID_TOKEN"
    message = "Invalid token"


# 403 Forbidden
class ForbiddenError(AscentBeaconError):
    """Raised when user lacks permission for an action."""
    
    status_code = 403
    error_code = "FORBIDDEN"
    message = "You don't have permission to perform this action"


class OwnershipError(ForbiddenError):
    """Raised when user tries to access another user's resource."""
    
    error_code = "OWNERSHIP_ERROR"
    message = "You don't own this resource"


# 404 Not Found
class NotFoundError(AscentBeaconError):
    """Raised when a requested resource doesn't exist."""
    
    status_code = 404
    error_code = "NOT_FOUND"
    message = "Resource not found"
    
    def __init__(
        self,
        resource_type: str = "Resource",
        resource_id: str | None = None,
    ) -> None:
        message = f"{resource_type} not found"
        details: dict[str, Any] = {"resource_type": resource_type}
        if resource_id:
            details["resource_id"] = resource_id
        super().__init__(message, details)


# 409 Conflict
class ConflictError(AscentBeaconError):
    """Raised when there's a conflict with existing data."""
    
    status_code = 409
    error_code = "CONFLICT"
    message = "Resource conflict"


class DuplicateError(ConflictError):
    """Raised when trying to create a duplicate resource."""
    
    error_code = "DUPLICATE"
    message = "Resource already exists"


# 422 Unprocessable Entity
class BusinessRuleError(AscentBeaconError):
    """Raised when a business rule is violated."""
    
    status_code = 422
    error_code = "BUSINESS_RULE_ERROR"
    message = "Operation violates business rules"


# 429 Too Many Requests
class RateLimitError(AscentBeaconError):
    """Raised when rate limit is exceeded."""
    
    status_code = 429
    error_code = "RATE_LIMIT_EXCEEDED"
    message = "Too many requests"


# 503 Service Unavailable
class ServiceUnavailableError(AscentBeaconError):
    """Raised when an external service is unavailable."""
    
    status_code = 503
    error_code = "SERVICE_UNAVAILABLE"
    message = "Service temporarily unavailable"


class LLMServiceError(ServiceUnavailableError):
    """Raised when LLM service fails."""
    
    error_code = "LLM_SERVICE_ERROR"
    message = "AI service temporarily unavailable"


class DatabaseError(ServiceUnavailableError):
    """Raised when database operations fail."""
    
    error_code = "DATABASE_ERROR"
    message = "Database service temporarily unavailable"
