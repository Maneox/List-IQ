# app/exceptions.py

class AppError(Exception):
    """Base class for application-specific errors."""
    pass

class ConfigurationError(AppError):
    """Raised when a configuration error is detected."""
    pass

class DataSourceError(AppError):
    """Base class for data source related errors."""
    pass

class CurlExecutionError(DataSourceError):
    """Raised when a curl command execution fails."""
    pass

class UnsupportedDataSourceError(DataSourceError):
    """Raised when an unsupported data source is requested."""
    pass
