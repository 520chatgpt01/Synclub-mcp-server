"""Custom exceptions for SynClub MCP."""

class SynclubAPIError(Exception):
    """Base exception for Synclub API errors."""
    pass

class SynclubAuthError(SynclubAPIError):
    """Authentication related errors."""
    pass

class SynclubRequestError(SynclubAPIError):
    """Request related errors."""
    pass

class SynclubTimeoutError(SynclubAPIError):
    """Timeout related errors."""
    pass

class SynclubValidationError(SynclubAPIError):
    """Validation related errors."""
    pass 

class SynclubMcpError(SynclubAPIError):
    pass
