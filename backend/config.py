import os
from typing import List
from dotenv import load_dotenv
import re

# Load environment variables from .env file
load_dotenv()

class Config:
    """
    Configuration class that manages application settings loaded from environment variables.
    
    This class handles the loading and validation of essential configuration parameters
    required for the application to function properly. It ensures all required environment
    variables are present and validates their values.
    """
    
    CORS_ORIGINS: List[str]
    """List of allowed origins for Cross-Origin Resource Sharing (CORS). 
    These are the domains that are allowed to make requests to the backend."""
    
    FRONTEND_PATH: str
    """Path to the frontend application directory. Used for serving static files."""
    
    COOKIE_DOMAIN: str
    """Domain for which cookies are valid. Used for session management and security."""
    
    BASE_URL: str
    """Base URL of the application. Must be a valid HTTP/HTTPS URL."""
    
    SESSION_MAX_AGE: int
    """Maximum age of a session in seconds. Controls how long user sessions remain valid."""

    def __init__(self):
        """
        Initialize the configuration by loading and validating all required environment variables.
        
        Raises:
            ValueError: If any required environment variable is missing or invalid.
        """
        # CORS configuration
        cors_origins = self._get_required_env("CORS_ORIGINS").split(",")
        self.CORS_ORIGINS = [self._validate_cors_origin(origin.strip()) for origin in cors_origins]

        # Frontend configuration
        frontend_path = self._get_required_env("FRONTEND_PATH")
        self.FRONTEND_PATH = self._validate_frontend_path(frontend_path)

        # Cookie configuration
        self.COOKIE_DOMAIN = self._get_required_env("COOKIE_DOMAIN")

        # Base URL configuration
        self.BASE_URL = self._validate_url(self._get_required_env("BASE_URL"))

        # Session configuration
        self.SESSION_MAX_AGE = int(self._get_required_env("SESSION_MAX_AGE"))

    def _get_required_env(self, key: str) -> str:
        """
        Get a required environment variable or raise an exception if missing.
        
        Args:
            key: The name of the environment variable to retrieve.
            
        Returns:
            The value of the environment variable.
            
        Raises:
            ValueError: If the environment variable is not set.
        """
        value = os.getenv(key)
        if value is None:
            raise ValueError(f"Missing required environment variable: {key}")
        return value

    def _validate_url(self, url: str) -> str:
        """
        Validate that a string is a proper URL.
        
        Args:
            url: The URL string to validate.
            
        Returns:
            The validated URL string.
            
        Raises:
            ValueError: If the URL does not start with 'http://' or 'https://'.
        """
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"Invalid URL format: {url}")
        return url

    def _validate_cors_origin(self, origin: str) -> str:
        """
        Validate that a CORS origin is either a valid URL or a valid domain.
        
        Args:
            origin: The CORS origin to validate.
            
        Returns:
            The validated origin string.
            
        Raises:
            ValueError: If the origin is not a valid URL or domain.
        """
        # Allow wildcard for development
        if origin == "*":
            return origin
            
        # Check if it's a valid URL
        if origin.startswith(("http://", "https://")):
            return self._validate_url(origin)
            
        # Check if it's a valid domain
        domain_pattern = r'^([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$'
        if re.match(domain_pattern, origin):
            return origin
            
        raise ValueError(f"Invalid CORS origin format: {origin}")

    def _validate_frontend_path(self, path: str) -> str:
        """
        Validate that the frontend path exists on the filesystem.
        
        Args:
            path: The path to validate.
            
        Returns:
            The validated path string.
            
        Raises:
            ValueError: If the path does not exist or is not a directory.
        """
        if not os.path.exists(path):
            raise ValueError(f"Frontend path does not exist: {path}")
        if not os.path.isdir(path):
            raise ValueError(f"Frontend path is not a directory: {path}")
        return os.path.abspath(path)

# Create a global configuration instance
config = Config() 