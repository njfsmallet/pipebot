import logging
import json
import uuid
import contextvars
from datetime import datetime
from typing import Any, Dict

# Create a context variable to store the correlation ID
correlation_id = contextvars.ContextVar('correlation_id', default=None)

# Configure the root logger once
def setup_logging() -> None:
    """Configure global application logging."""
    # Remove all existing handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Configure basic logging
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Add console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    root_logger.setLevel(logging.INFO)
    
    # Disable verbose logging from third-party libraries
    logging.getLogger('botocore').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('redis').setLevel(logging.WARNING)

class StructuredLogger:
    """Custom logger for structured and consistent logging."""
    
    def __init__(self, name: str, level: int = logging.INFO):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)

    def _format_message(self, message: str, **kwargs: Any) -> str:
        """Format message with additional metadata."""
        current_correlation_id = correlation_id.get() or str(uuid.uuid4())

        log_data = {
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "correlation_id": current_correlation_id,
            **kwargs
        }
        return json.dumps(log_data)

    @staticmethod
    def set_correlation_id(id_value: str = None) -> str:
        """Set a correlation ID for the current context or generate a new one."""
        new_id = id_value or str(uuid.uuid4())
        correlation_id.set(new_id)
        return new_id

    def info(self, message: str, **kwargs: Any) -> None:
        """Log an INFO level message."""
        self.logger.info(self._format_message(message, **kwargs))

    def error(self, message: str, **kwargs: Any) -> None:
        """Log an ERROR level message."""
        self.logger.error(self._format_message(message, **kwargs))

    def debug(self, message: str, **kwargs: Any) -> None:
        """Log a DEBUG level message."""
        self.logger.debug(self._format_message(message, **kwargs))

    def warning(self, message: str, **kwargs: Any) -> None:
        """Log a WARNING level message."""
        self.logger.warning(self._format_message(message, **kwargs)) 