import logging
import json
import os
from datetime import datetime
from typing import Any, Dict

class StructuredLogger:
    """Custom logger for structured and consistent logging."""
    
    def __init__(self, name: str, level: int = None):
        self.logger = logging.getLogger(name)
        
        # Get log level from environment variable or use default
        if level is None:
            level = getattr(logging, os.getenv('LOG_LEVEL', 'INFO'))
        
        self.logger.setLevel(level)
        
        # Remove any existing handlers to avoid duplicates
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)
        
        # Base format for logs
        self.formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # Console handler with formatting for non-INFO logs
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(self.formatter)
        console_handler.addFilter(lambda record: record.levelno != logging.INFO)
        self.logger.addHandler(console_handler)

        # Raw console handler without formatting for INFO logs
        self.raw_handler = logging.StreamHandler()
        self.raw_handler.setFormatter(logging.Formatter('%(message)s'))
        self.raw_handler.addFilter(lambda record: record.levelno == logging.INFO)
        self.logger.addHandler(self.raw_handler)

        # Configure logging levels for third-party libraries
        logging.getLogger('botocore.credentials').setLevel(logging.WARNING)
        logging.getLogger('urllib3').setLevel(logging.WARNING)
        logging.getLogger('redis').setLevel(logging.WARNING)

    def info(self, message: str, **kwargs: Any) -> None:
        """Log an INFO level message without formatting."""
        if kwargs:
            self.logger.info(f"{message} {json.dumps(kwargs)}")
        else:
            self.logger.info(message)

    def error(self, message: str, **kwargs: Any) -> None:
        """Log an ERROR level message with formatting."""
        if kwargs:
            self.logger.error(f"{message} {json.dumps(kwargs)}")
        else:
            self.logger.error(message)

    def debug(self, message: str, **kwargs: Any) -> None:
        """Log a DEBUG level message with formatting."""
        if kwargs:
            self.logger.debug(f"{message} {json.dumps(kwargs)}")
        else:
            self.logger.debug(message)

    def warning(self, message: str, **kwargs: Any) -> None:
        """Log a WARNING level message with formatting."""
        if kwargs:
            self.logger.warning(f"{message} {json.dumps(kwargs)}")
        else:
            self.logger.warning(message)

    def success(self, message: str, **kwargs: Any) -> None:
        """Log a SUCCESS level message with formatting."""
        if kwargs:
            self.logger.info(f"{message} {json.dumps(kwargs)}")
        else:
            self.logger.info(message)

    def raw(self, message: str) -> None:
        """Log a message without any formatting."""
        self.raw_logger.info(message)
