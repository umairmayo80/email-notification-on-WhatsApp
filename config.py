import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def get_positive_int_env(name: str, default: int) -> int:
    """Read a positive integer from the environment with a safe default."""
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default

    return value if value > 0 else default


class Config:
    # Email configuration
    EMAIL_HOST = os.getenv('EMAIL_HOST', 'imap.gmail.com')
    EMAIL_PORT = int(os.getenv('EMAIL_PORT', '993'))
    EMAIL_USERNAME = os.getenv('EMAIL_USERNAME')
    EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
    
    # WhatsApp configuration
    WHATSAPP_PHONE_NUMBER = os.getenv('WHATSAPP_PHONE_NUMBER')  # Format: +1234567890
    
    # Monitoring settings
    CHECK_INTERVAL_MINUTES = float(os.getenv('CHECK_INTERVAL_MINUTES', '5'))
    MAX_EMAILS_PER_CHECK = get_positive_int_env('MAX_EMAILS_PER_CHECK', 3)
    KEYWORDS_TO_MONITOR = os.getenv('KEYWORDS_TO_MONITOR', '').split(',') if os.getenv('KEYWORDS_TO_MONITOR') else []
    
    # Sender filtering (optional)
    MONITOR_SPECIFIC_SENDERS = os.getenv('MONITOR_SPECIFIC_SENDERS', '').split(',') if os.getenv('MONITOR_SPECIFIC_SENDERS') else []
    
    @classmethod
    def validate_config(cls):
        """Validate that all required configuration is present"""
        required_fields = [
            'EMAIL_USERNAME',
            'EMAIL_PASSWORD',
            'WHATSAPP_PHONE_NUMBER'
        ]
        
        missing_fields = []
        for field in required_fields:
            if not getattr(cls, field):
                missing_fields.append(field)
        
        if missing_fields:
            raise ValueError(f"Missing required configuration: {', '.join(missing_fields)}")
        
        return True
