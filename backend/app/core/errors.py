"""Domain exceptions. Mapped to HTTP responses in app.main."""


class DomainError(Exception):
    status_code = 400
    code = "error"

    def __init__(self, detail: str, code: str | None = None):
        super().__init__(detail)
        self.detail = detail
        if code:
            self.code = code


class NotFoundError(DomainError):
    status_code = 404
    code = "not_found"


class PermissionDeniedError(DomainError):
    status_code = 403
    code = "permission_denied"


class BusinessRuleError(DomainError):
    """The request is well-formed but violates a business rule."""

    status_code = 422
    code = "business_rule"


class ConflictError(DomainError):
    """State conflict: insufficient stock, wrong document status, concurrent modification."""

    status_code = 409
    code = "conflict"


class InsufficientStockError(ConflictError):
    code = "insufficient_stock"
