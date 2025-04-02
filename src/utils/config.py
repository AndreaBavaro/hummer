"""
Configuration management for the Zoom Interview Analysis System.
"""

import os
from pydantic import BaseModel
from typing import Optional, Literal

class Config(BaseModel):
    """Configuration class for the Zoom Interview Analysis System."""
    
    # General configuration
    debug: bool = False
    storage_mode: Literal["local", "cloud"] = "local"
    
    # Paths
    local_storage_path: str = "./data"
    temp_storage_path: str = "./temp"
    
    # Zoom Bot Configuration
    zoom_email: Optional[str] = None
    zoom_password: Optional[str] = None
    zoom_api_key: Optional[str] = None
    zoom_api_secret: Optional[str] = None
    
    # Attendee API Configuration
    attendee_api_key: Optional[str] = None
    zoom_oauth_client_id: Optional[str] = None  # Configured on Attendee dashboard
    zoom_oauth_client_secret: Optional[str] = None  # Configured on Attendee dashboard
    deepgram_api_key: Optional[str] = None  # Configured on Attendee dashboard
    
    # AWS Configuration
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_region: str = "us-east-1"
    s3_bucket_name: Optional[str] = None
    
    # Hume AI Configuration
    hume_api_key: Optional[str] = None
    
    # Anthropic API Configuration
    anthropic_api_key: Optional[str] = None
    
    # Email Configuration
    email_service: Literal["ses", "mailjet", "smtp"] = "ses"
    email_from: Optional[str] = None
    email_from_name: str = "Zoom Interview Analysis System"
    
    # SES Configuration
    ses_region: str = "us-east-1"
    
    # Mailjet Configuration
    mailjet_api_key: Optional[str] = None
    mailjet_secret_key: Optional[str] = None
    
    # SMTP Configuration
    smtp_server: Optional[str] = None
    smtp_port: int = 587
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_use_tls: bool = True
    
    def __init__(self, **data):
        """Initialize configuration from environment variables and passed data."""
        # Load environment variables
        env_data = {
            "debug": os.getenv("DEBUG", "False").lower() == "true",
            "storage_mode": os.getenv("STORAGE_MODE", "local"),
            "local_storage_path": os.getenv("LOCAL_STORAGE_PATH", "./data"),
            "temp_storage_path": os.getenv("TEMP_STORAGE_PATH", "./temp"),
            
            # Zoom Bot Configuration
            "zoom_email": os.getenv("ZOOM_EMAIL"),
            "zoom_password": os.getenv("ZOOM_PASSWORD"),
            "zoom_api_key": os.getenv("ZOOM_API_KEY"),
            "zoom_api_secret": os.getenv("ZOOM_API_SECRET"),
            
            # Attendee API Configuration
            "attendee_api_key": os.getenv("ATTENDEE_API_KEY"),
            "zoom_oauth_client_id": os.getenv("ZOOM_OAUTH_CLIENT_ID"),
            "zoom_oauth_client_secret": os.getenv("ZOOM_OAUTH_CLIENT_SECRET"),
            "deepgram_api_key": os.getenv("DEEPGRAM_API_KEY"),
            
            # AWS Configuration
            "aws_access_key_id": os.getenv("AWS_ACCESS_KEY_ID"),
            "aws_secret_access_key": os.getenv("AWS_SECRET_ACCESS_KEY"),
            "aws_region": os.getenv("AWS_REGION", "us-east-1"),
            "s3_bucket_name": os.getenv("S3_BUCKET_NAME"),
            
            # Hume AI Configuration
            "hume_api_key": os.getenv("HUME_API_KEY"),
            
            # Anthropic API Configuration
            "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY"),
            
            # Email Configuration
            "email_service": os.getenv("EMAIL_SERVICE", "ses"),
            "email_from": os.getenv("EMAIL_FROM"),
            "email_from_name": os.getenv("EMAIL_FROM_NAME", "Zoom Interview Analysis System"),
            
            # SES Configuration
            "ses_region": os.getenv("SES_REGION", "us-east-1"),
            
            # Mailjet Configuration
            "mailjet_api_key": os.getenv("MAILJET_API_KEY"),
            "mailjet_secret_key": os.getenv("MAILJET_SECRET_KEY"),
            
            # SMTP Configuration
            "smtp_server": os.getenv("SMTP_SERVER"),
            "smtp_port": int(os.getenv("SMTP_PORT", "587")),
            "smtp_username": os.getenv("SMTP_USERNAME"),
            "smtp_password": os.getenv("SMTP_PASSWORD"),
            "smtp_use_tls": os.getenv("SMTP_USE_TLS", "True").lower() == "true",
        }
        
        # Override environment variables with passed data
        env_data.update(data)
        
        super().__init__(**env_data)
        
        # Create storage directories if they don't exist
        self._create_directories()
    
    def _create_directories(self):
        """Create necessary directories if they don't exist."""
        os.makedirs(self.local_storage_path, exist_ok=True)
        os.makedirs(self.temp_storage_path, exist_ok=True)
        
    def validate_config(self):
        """Validate that all required configuration is present."""
        if self.storage_mode == "cloud":
            assert self.aws_access_key_id, "AWS_ACCESS_KEY_ID is required for cloud storage"
            assert self.aws_secret_access_key, "AWS_SECRET_ACCESS_KEY is required for cloud storage"
            assert self.s3_bucket_name, "S3_BUCKET_NAME is required for cloud storage"
        
        # Validate Attendee API credentials
        assert self.attendee_api_key, "ATTENDEE_API_KEY is required for Zoom meeting automation"
        
        assert self.hume_api_key, "HUME_API_KEY is required for analytics processing"
        assert self.anthropic_api_key, "ANTHROPIC_API_KEY is required for LLM insights"
        
        if self.email_service == "ses":
            assert self.aws_access_key_id, "AWS_ACCESS_KEY_ID is required for SES"
            assert self.aws_secret_access_key, "AWS_SECRET_ACCESS_KEY is required for SES"
        elif self.email_service == "mailjet":
            assert self.mailjet_api_key, "MAILJET_API_KEY is required for Mailjet"
            assert self.mailjet_secret_key, "MAILJET_SECRET_KEY is required for Mailjet"
        elif self.email_service == "smtp":
            assert self.smtp_server, "SMTP_SERVER is required for SMTP"
            assert self.smtp_username, "SMTP_USERNAME is required for SMTP"
            assert self.smtp_password, "SMTP_PASSWORD is required for SMTP"
        
        assert self.email_from, "EMAIL_FROM is required for sending emails"
