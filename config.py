import os
from typing import Dict, Iterable, Optional, Tuple

from dotenv import dotenv_values


CONFIG_FIELD_NAMES = (
    'EMAIL_HOST',
    'EMAIL_PORT',
    'EMAIL_USERNAME',
    'EMAIL_PASSWORD',
    'NOTIFY_EMAIL_RECIPIENTS',
    'SMTP_HOST',
    'SMTP_PORT',
    'SMTP_USERNAME',
    'SMTP_PASSWORD',
    'SMTP_FROM',
    'SMTP_TIMEOUT_SECONDS',
    'EMAIL_NOTIFICATION_SUBJECT_PREFIX',
    'EMAIL_NOTIFICATION_BODY_INTRO',
    'WHATSAPP_PHONE_NUMBER',
    'WHATSAPP_GROUP_INVITE_CODE',
    'WHATSAPP_CHROME_PROFILE_DIR',
    'WHATSAPP_WAIT_SECONDS',
    'WHATSAPP_MAX_RETRIES',
    'WHATSAPP_RETRY_DELAY_SECONDS',
    'WHATSAPP_HEADLESS',
    'WHATSAPP_HEADLESS_WINDOW_SIZE',
    'WHATSAPP_DEBUG_SCREENSHOT_DIR',
    'WHATSAPP_MESSAGE_HEADER',
    'CHROME_BINARY_PATH',
    'CHECK_INTERVAL_MINUTES',
    'CONFIG_RELOAD_INTERVAL_SECONDS',
    'MAX_EMAILS_PER_CHECK',
    'EMAIL_SCAN_MULTIPLIER',
    'NOTIFICATION_DELAY_SECONDS',
    'KEYWORDS_TO_MONITOR',
    'NOTIFICATION_STATE_FILE',
    'MONITOR_SPECIFIC_SENDERS',
)

SECRET_CONFIG_KEYS = {
    'EMAIL_PASSWORD',
    'SMTP_PASSWORD',
}

IMAP_CONNECTION_CONFIG_KEYS = {
    'EMAIL_HOST',
    'EMAIL_PORT',
    'EMAIL_USERNAME',
    'EMAIL_PASSWORD',
}

WHATSAPP_DRIVER_CONFIG_KEYS = {
    'WHATSAPP_CHROME_PROFILE_DIR',
    'WHATSAPP_HEADLESS',
    'WHATSAPP_HEADLESS_WINDOW_SIZE',
    'CHROME_BINARY_PATH',
}

RESTART_REQUIRED_CONFIG_KEYS = {
    'NOTIFICATION_STATE_FILE',
}


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
    """Runtime configuration loaded from environment variables and .env."""

    def __init__(self, env_path: str = '.env', values: Optional[Dict[str, str]] = None):
        self.env_path = env_path
        self._env_file_signature = self._get_env_file_signature(env_path)
        self._values = values if values is not None else self._load_values(env_path)
        self._load_config_values()

    def _load_values(self, env_path: str) -> Dict[str, str]:
        values = dict(os.environ)
        env_file_values = {
            key: value
            for key, value in dotenv_values(env_path).items()
            if value is not None
        }
        values.update(env_file_values)
        return values

    def _load_config_values(self):
        # Email configuration
        self.EMAIL_HOST = self._get('EMAIL_HOST', 'imap.gmail.com')
        self.EMAIL_PORT = self._get_positive_int('EMAIL_PORT', 993)
        self.EMAIL_USERNAME = self._get('EMAIL_USERNAME')
        self.EMAIL_PASSWORD = self._get('EMAIL_PASSWORD')

        # Outbound email notification configuration
        self.NOTIFY_EMAIL_RECIPIENTS = self._get_list('NOTIFY_EMAIL_RECIPIENTS')
        self.SMTP_HOST = self._get('SMTP_HOST', 'smtp.gmail.com')
        self.SMTP_PORT = self._get_positive_int('SMTP_PORT', 465)
        self.SMTP_USERNAME = self._get('SMTP_USERNAME') or self.EMAIL_USERNAME
        self.SMTP_PASSWORD = self._get('SMTP_PASSWORD') or self.EMAIL_PASSWORD
        self.SMTP_FROM = self._get('SMTP_FROM') or self.SMTP_USERNAME or self.EMAIL_USERNAME
        self.SMTP_TIMEOUT_SECONDS = self._get_positive_int('SMTP_TIMEOUT_SECONDS', 30)
        self.EMAIL_NOTIFICATION_SUBJECT_PREFIX = (
            self._get('EMAIL_NOTIFICATION_SUBJECT_PREFIX', 'Upwork Alert').strip()
            or 'Upwork Alert'
        )
        self.EMAIL_NOTIFICATION_BODY_INTRO = (
            self._get(
                'EMAIL_NOTIFICATION_BODY_INTRO',
                'New Upwork alert matched your notification rule.',
            ).strip()
            or 'New Upwork alert matched your notification rule.'
        )

        # WhatsApp configuration
        self.WHATSAPP_PHONE_NUMBER = self._get('WHATSAPP_PHONE_NUMBER')
        self.WHATSAPP_GROUP_INVITE_CODE = self._get('WHATSAPP_GROUP_INVITE_CODE', '').strip()
        self.WHATSAPP_CHROME_PROFILE_DIR = self._get(
            'WHATSAPP_CHROME_PROFILE_DIR',
            '.whatsapp_chrome_profile',
        )
        self.WHATSAPP_WAIT_SECONDS = self._get_positive_int('WHATSAPP_WAIT_SECONDS', 90)
        self.WHATSAPP_MAX_RETRIES = self._get_positive_int('WHATSAPP_MAX_RETRIES', 3)
        self.WHATSAPP_RETRY_DELAY_SECONDS = self._get_non_negative_int(
            'WHATSAPP_RETRY_DELAY_SECONDS',
            300,
        )
        self.WHATSAPP_HEADLESS = self._get_bool('WHATSAPP_HEADLESS', False)
        self.WHATSAPP_HEADLESS_WINDOW_SIZE = self._get(
            'WHATSAPP_HEADLESS_WINDOW_SIZE',
            '1280,900',
        ).strip()
        self.WHATSAPP_DEBUG_SCREENSHOT_DIR = self._get(
            'WHATSAPP_DEBUG_SCREENSHOT_DIR',
            'debug_screenshots',
        ).strip()
        self.WHATSAPP_MESSAGE_HEADER = (
            self._get('WHATSAPP_MESSAGE_HEADER', 'Upwork Alert').strip()
            or 'Upwork Alert'
        )
        self.CHROME_BINARY_PATH = self._get('CHROME_BINARY_PATH')

        # Monitoring settings
        self.CHECK_INTERVAL_MINUTES = self._get_positive_float('CHECK_INTERVAL_MINUTES', 5)
        self.CONFIG_RELOAD_INTERVAL_SECONDS = self._get_positive_int(
            'CONFIG_RELOAD_INTERVAL_SECONDS',
            60,
        )
        self.MAX_EMAILS_PER_CHECK = self._get_positive_int('MAX_EMAILS_PER_CHECK', 3)
        self.EMAIL_SCAN_MULTIPLIER = self._get_positive_int('EMAIL_SCAN_MULTIPLIER', 5)
        self.NOTIFICATION_DELAY_SECONDS = self._get_non_negative_int(
            'NOTIFICATION_DELAY_SECONDS',
            2,
        )
        self.KEYWORDS_TO_MONITOR = self._get_list('KEYWORDS_TO_MONITOR')
        self.NOTIFICATION_STATE_FILE = self._get(
            'NOTIFICATION_STATE_FILE',
            'notification_state.json',
        )

        # Sender filtering (optional)
        self.MONITOR_SPECIFIC_SENDERS = self._get_list('MONITOR_SPECIFIC_SENDERS')

    def _get(self, name: str, default: Optional[str] = None) -> Optional[str]:
        value = self._values.get(name)
        return default if value is None else value

    def _get_list(self, name: str):
        value = self._get(name, '') or ''
        return [item.strip() for item in value.split(',') if item.strip()]

    def _get_bool(self, name: str, default: bool = False) -> bool:
        value = self._get(name)
        if value is None:
            return default

        normalized = value.strip().lower()
        if normalized in ('1', 'true', 'yes', 'y', 'on'):
            return True
        if normalized in ('0', 'false', 'no', 'n', 'off'):
            return False

        return default

    def _get_positive_int(self, name: str, default: int) -> int:
        try:
            value = int(self._get(name, str(default)))
        except (TypeError, ValueError):
            return default

        return value if value > 0 else default

    def _get_non_negative_int(self, name: str, default: int) -> int:
        try:
            value = int(self._get(name, str(default)))
        except (TypeError, ValueError):
            return default

        return value if value >= 0 else default

    def _get_positive_float(self, name: str, default: float) -> float:
        try:
            value = float(self._get(name, str(default)))
        except (TypeError, ValueError):
            return default

        return value if value > 0 else default

    def reload(self):
        """Return a new Config loaded from the same .env path."""
        return self.__class__(env_path=self.env_path)

    def env_file_changed(self) -> bool:
        """Return True when the .env file stat changed since this config loaded."""
        return self._get_env_file_signature(self.env_path) != self._env_file_signature

    def as_dict(self) -> Dict[str, object]:
        return {name: getattr(self, name) for name in CONFIG_FIELD_NAMES}

    def changed_keys(self, other: 'Config') -> set:
        current = self.as_dict()
        incoming = other.as_dict()
        return {
            key
            for key in CONFIG_FIELD_NAMES
            if current.get(key) != incoming.get(key)
        }

    @staticmethod
    def safe_changed_keys(keys: Iterable[str]):
        return sorted(key for key in keys if key not in SECRET_CONFIG_KEYS)

    @staticmethod
    def _get_env_file_signature(env_path: str) -> Optional[Tuple[int, int]]:
        try:
            stat = os.stat(env_path)
        except OSError:
            return None

        return (stat.st_mtime_ns, stat.st_size)

    def validate_config(self):
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
            if not getattr(self, field):
                missing_fields.append(field)
        
        if missing_fields:
            raise ValueError(f"Missing required configuration: {', '.join(missing_fields)}")

        if not self.WHATSAPP_PHONE_NUMBER and not self.WHATSAPP_GROUP_INVITE_CODE:
            raise ValueError(
                "Missing required configuration: WHATSAPP_PHONE_NUMBER or "
                "WHATSAPP_GROUP_INVITE_CODE"
            )
        
        return True
