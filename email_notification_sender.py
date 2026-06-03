import logging
import smtplib
from email.message import EmailMessage
from typing import Dict

from config import Config


class EmailNotificationSender:
    """Send email notifications before the WhatsApp attempt."""

    def __init__(self):
        self.config = Config()
        self.logger = logging.getLogger(__name__)

    def send_email_notification(self, email_data: Dict) -> bool:
        """Send a notification email for a source inbox message."""
        try:
            if not self.config.NOTIFY_EMAIL_RECIPIENTS:
                self.logger.error("No notification email recipients configured")
                return False

            message = self._build_message(email_data)

            with smtplib.SMTP_SSL(
                self.config.SMTP_HOST,
                self.config.SMTP_PORT,
                timeout=self.config.SMTP_TIMEOUT_SECONDS,
            ) as smtp:
                smtp.login(self.config.SMTP_USERNAME, self.config.SMTP_PASSWORD)
                smtp.send_message(message)

            self.logger.info(
                "Email notification sent for source email UID %s",
                email_data.get('id'),
            )
            return True

        except Exception as e:
            self.logger.error("Failed to send email notification: %s", str(e))
            return False

    def _build_message(self, email_data: Dict) -> EmailMessage:
        subject = email_data.get('subject') or 'No Subject'
        sender = email_data.get('sender') or 'Unknown Sender'
        date = email_data.get('date') or 'Unknown Date'
        body = email_data.get('body') or ''

        notification = EmailMessage()
        notification['From'] = self.config.SMTP_FROM
        notification['To'] = ', '.join(self.config.NOTIFY_EMAIL_RECIPIENTS)
        notification['Subject'] = (
            f"{self.config.EMAIL_NOTIFICATION_SUBJECT_PREFIX}: {subject}"
        )
        notification.set_content(
            f"{self.config.EMAIL_NOTIFICATION_BODY_INTRO}\n\n"
            f"From: {sender}\n"
            f"Subject: {subject}\n"
            f"Date: {date}\n\n"
            f"Preview:\n{body}"
        )

        return notification
