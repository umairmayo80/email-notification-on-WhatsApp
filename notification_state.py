import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional


class NotificationState:
    """Persist notification progress so email is not resent during WhatsApp retries."""

    def __init__(self, path: str = 'notification_state.json'):
        self.path = path
        self.logger = logging.getLogger(__name__)
        self.data = self._load()

    def _load(self) -> Dict:
        if not os.path.exists(self.path):
            return {'notifications': {}}

        try:
            with open(self.path, 'r', encoding='utf-8') as state_file:
                data = json.load(state_file)
        except (json.JSONDecodeError, OSError) as e:
            self.logger.error("Could not load notification state: %s", str(e))
            return {'notifications': {}}

        if not isinstance(data, dict):
            return {'notifications': {}}
        data.setdefault('notifications', {})
        return data

    def save(self):
        directory = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(directory, exist_ok=True)
        temp_path = f"{self.path}.tmp"

        with open(temp_path, 'w', encoding='utf-8') as state_file:
            json.dump(self.data, state_file, indent=2, sort_keys=True)

        os.replace(temp_path, self.path)

    def get(self, email_id: str) -> Optional[Dict]:
        return self.data.get('notifications', {}).get(str(email_id))

    def has_email_sent(self, email_id: str) -> bool:
        entry = self.get(email_id)
        return bool(entry and entry.get('email_sent'))

    def record_email_sent(self, email_data: Dict, message: str):
        email_id = str(email_data['id'])
        entry = self._entry(email_id, email_data, message)
        entry['email_sent'] = True
        entry['email_sent_at'] = entry.get('email_sent_at') or self._now_iso()
        entry.setdefault('status', 'queued')
        entry.setdefault('attempt_count', 0)
        entry.setdefault('next_attempt_at', None)
        self.save()

    def whatsapp_attempts_exhausted(self, email_id: str, max_retries: int) -> bool:
        entry = self.get(email_id)
        return bool(entry and int(entry.get('attempt_count', 0)) >= max_retries)

    def is_whatsapp_terminal(self, email_id: str) -> bool:
        entry = self.get(email_id)
        return bool(entry and entry.get('status') in ('sent', 'exhausted'))

    def is_whatsapp_due(self, email_id: str) -> bool:
        entry = self.get(email_id)
        if not entry or entry.get('status') in ('sent', 'exhausted'):
            return False

        next_attempt_at = entry.get('next_attempt_at')
        if not next_attempt_at:
            return True

        due_at = self._parse_time(next_attempt_at)
        return due_at is None or due_at <= self._now()

    def record_whatsapp_result(
        self,
        email_data: Dict,
        message: str,
        success: bool,
        max_retries: int,
        retry_delay_seconds: int,
        error: Optional[str] = None,
    ) -> Dict:
        email_id = str(email_data['id'])
        now = self._now()
        entry = self._entry(email_id, email_data, message)
        attempt_count = int(entry.get('attempt_count', 0)) + 1

        entry['attempt_count'] = attempt_count
        entry['last_attempt_at'] = self._format_time(now)
        entry['last_error'] = None if success else (error or 'WhatsApp send failed')

        if success:
            entry['status'] = 'sent'
            entry['sent_at'] = self._format_time(now)
            entry['next_attempt_at'] = None
        elif attempt_count >= max_retries:
            entry['status'] = 'exhausted'
            entry['exhausted_at'] = self._format_time(now)
            entry['next_attempt_at'] = None
        else:
            entry['status'] = 'queued'
            entry['next_attempt_at'] = self._format_time(
                now + timedelta(seconds=retry_delay_seconds)
            )

        self.save()
        return entry

    def record_whatsapp_exhausted(self, email_id: str):
        entry = self.get(email_id)
        if not entry:
            return

        entry['status'] = 'exhausted'
        entry['exhausted_at'] = entry.get('exhausted_at') or self._now_iso()
        entry['next_attempt_at'] = None
        self.save()

    def get_due_whatsapp_notifications(self, max_retries: int) -> List[Dict]:
        due_notifications = []

        for email_id, entry in self.data.get('notifications', {}).items():
            if not entry.get('email_sent'):
                continue
            if entry.get('status') in ('sent', 'exhausted'):
                continue
            if self.whatsapp_attempts_exhausted(email_id, max_retries):
                due_notifications.append(entry)
                continue
            if self.is_whatsapp_due(email_id):
                due_notifications.append(entry)

        return due_notifications

    def _entry(self, email_id: str, email_data: Dict, message: str) -> Dict:
        notifications = self.data.setdefault('notifications', {})
        entry = notifications.setdefault(
            email_id,
            {
                'created_at': self._now_iso(),
                'attempt_count': 0,
                'status': 'queued',
            },
        )
        entry['email_data'] = email_data
        entry['message'] = message
        return entry

    def _now_iso(self) -> str:
        return self._format_time(self._now())

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _format_time(value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _parse_time(value: str) -> Optional[datetime]:
        try:
            parsed = datetime.fromisoformat(value)
        except (TypeError, ValueError):
            return None

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
