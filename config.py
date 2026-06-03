import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def get_list_env(name: str):
    """Read a comma-separated environment variable as a cleaned list."""
    value = os.getenv(name, '')
    return [item.strip() for item in value.split(',') if item.strip()]


def get_bool_env(name: str, default: bool = False) -> bool:
    """Read a boolean environment variable with a safe default."""
    value = os.getenv(name)
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in ('1', 'true', 'yes', 'y', 'on'):
        return True
    if normalized in ('0', 'false', 'no', 'n', 'off'):
        return False

    return default


def get_positive_int_env(name: str, default: int) -> int:
    """Read a positive integer from the environment with a safe default."""
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default

    return value if value > 0 else default


def get_non_negative_int_env(name: str, default: int) -> int:
    """Read a non-negative integer from the environment with a safe default."""
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default

    return value if value >= 0 else default


def get_positive_float_env(name: str, default: float) -> float:
    """Read a positive float from the environment with a safe default."""
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default

    return value if value > 0 else default


class Config:
    # Email configuration
    EMAIL_HOST = os.getenv('EMAIL_HOST', 'imap.gmail.com')
    EMAIL_PORT = get_positive_int_env('EMAIL_PORT', 993)
    EMAIL_USERNAME = os.getenv('EMAIL_USERNAME')
    EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')

    # Outbound email notification configuration
    NOTIFY_EMAIL_RECIPIENTS = get_list_env('NOTIFY_EMAIL_RECIPIENTS')
    SMTP_HOST = os.getenv('SMTP_HOST', 'smtp.gmail.com')
    SMTP_PORT = get_positive_int_env('SMTP_PORT', 465)
    SMTP_USERNAME = os.getenv('SMTP_USERNAME') or EMAIL_USERNAME
    SMTP_PASSWORD = os.getenv('SMTP_PASSWORD') or EMAIL_PASSWORD
    SMTP_FROM = os.getenv('SMTP_FROM') or SMTP_USERNAME or EMAIL_USERNAME
    SMTP_TIMEOUT_SECONDS = get_positive_int_env('SMTP_TIMEOUT_SECONDS', 30)
    EMAIL_NOTIFICATION_SUBJECT_PREFIX = (
        os.getenv('EMAIL_NOTIFICATION_SUBJECT_PREFIX', 'Upwork Alert').strip()
        or 'Upwork Alert'
    )
    EMAIL_NOTIFICATION_BODY_INTRO = (
        os.getenv(
            'EMAIL_NOTIFICATION_BODY_INTRO',
            'New Upwork alert matched your notification rule.',
        ).strip()
        or 'New Upwork alert matched your notification rule.'
    )
    
    # WhatsApp configuration
    WHATSAPP_PHONE_NUMBER = os.getenv('WHATSAPP_PHONE_NUMBER')  # Format: +1234567890
    WHATSAPP_GROUP_INVITE_CODE = os.getenv('WHATSAPP_GROUP_INVITE_CODE', '').strip()
    WHATSAPP_CHROME_PROFILE_DIR = os.getenv('WHATSAPP_CHROME_PROFILE_DIR', '.whatsapp_chrome_profile')
    WHATSAPP_WAIT_SECONDS = get_positive_int_env('WHATSAPP_WAIT_SECONDS', 90)
    WHATSAPP_MAX_RETRIES = get_positive_int_env('WHATSAPP_MAX_RETRIES', 3)
    WHATSAPP_RETRY_DELAY_SECONDS = get_non_negative_int_env('WHATSAPP_RETRY_DELAY_SECONDS', 300)
    WHATSAPP_HEADLESS = get_bool_env('WHATSAPP_HEADLESS', False)
    WHATSAPP_HEADLESS_WINDOW_SIZE = os.getenv('WHATSAPP_HEADLESS_WINDOW_SIZE', '1280,900').strip()
    WHATSAPP_DEBUG_SCREENSHOT_DIR = os.getenv('WHATSAPP_DEBUG_SCREENSHOT_DIR', 'debug_screenshots').strip()
    WHATSAPP_MESSAGE_HEADER = os.getenv('WHATSAPP_MESSAGE_HEADER', 'Upwork Alert').strip() or 'Upwork Alert'
    CHROME_BINARY_PATH = os.getenv('CHROME_BINARY_PATH')
    
    # Monitoring settings
    CHECK_INTERVAL_MINUTES = get_positive_float_env('CHECK_INTERVAL_MINUTES', 5)
    MAX_EMAILS_PER_CHECK = get_positive_int_env('MAX_EMAILS_PER_CHECK', 3)
    EMAIL_SCAN_MULTIPLIER = get_positive_int_env('EMAIL_SCAN_MULTIPLIER', 5)
    NOTIFICATION_DELAY_SECONDS = get_non_negative_int_env('NOTIFICATION_DELAY_SECONDS', 2)
    KEYWORDS_TO_MONITOR = get_list_env('KEYWORDS_TO_MONITOR')
    NOTIFICATION_STATE_FILE = os.getenv('NOTIFICATION_STATE_FILE', 'notification_state.json')
    
    # Sender filtering (optional)
    MONITOR_SPECIFIC_SENDERS = get_list_env('MONITOR_SPECIFIC_SENDERS')
    
    @classmethod
    def validate_config(cls):
        """Validate that all required configuration is present"""
        required_fields = [
            'EMAIL_USERNAME',
            'EMAIL_PASSWORD',
            'NOTIFY_EMAIL_RECIPIENTS',
            'SMTP_USERNAME',
            'SMTP_PASSWORD',
            'SMTP_FROM',
        ]
        
        missing_fields = []
        for field in required_fields:
            if not getattr(cls, field):
                missing_fields.append(field)
        
        if missing_fields:
            raise ValueError(f"Missing required configuration: {', '.join(missing_fields)}")

        if not cls.WHATSAPP_PHONE_NUMBER and not cls.WHATSAPP_GROUP_INVITE_CODE:
            raise ValueError(
                "Missing required configuration: WHATSAPP_PHONE_NUMBER or "
                "WHATSAPP_GROUP_INVITE_CODE"
            )
        
        return True
