#!/usr/bin/env python3
"""
Email to WhatsApp Notification System
Monitors email inbox and sends WhatsApp notifications for new emails
"""

import time
import schedule
import logging
from email_monitor import EmailMonitor
from email_notification_sender import EmailNotificationSender
from notification_state import NotificationState
from whatsapp_sender import WhatsAppSender
from config import Config

class EmailToWhatsAppNotifier:
    def __init__(self):
        self.email_monitor = EmailMonitor()
        self.email_sender = EmailNotificationSender()
        self.whatsapp_sender = WhatsAppSender()
        self.config = Config()
        self.notification_state = NotificationState(self.config.NOTIFICATION_STATE_FILE)
        
        # Set up logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('notifier.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def validate_configuration(self) -> bool:
        """Validate all required configuration"""
        try:
            self.config.validate_config()
            if not self.whatsapp_sender.validate_phone_number():
                return False
            self.logger.info("Configuration validation passed")
            return True
        except ValueError as e:
            self.logger.error(f"Configuration validation failed: {str(e)}")
            return False
    
    def check_emails_and_notify(self):
        """Check for new emails, send email first, then WhatsApp."""
        try:
            self.logger.info("Checking for new emails...")
            
            # Get new emails
            new_emails = self.email_monitor.get_new_emails()
            processed_email_ids = set()
            
            if not new_emails:
                self.logger.info("No new emails found")
            else:
                self.logger.info(f"Found {len(new_emails)} new email(s)")
            
            for email_data in new_emails:
                processed_email_ids.add(str(email_data['id']))
                self.handle_email_notification(email_data)
                
                if self.config.NOTIFICATION_DELAY_SECONDS:
                    time.sleep(self.config.NOTIFICATION_DELAY_SECONDS)

            self.process_due_whatsapp_retries(exclude_email_ids=processed_email_ids)
        
        except Exception as e:
            self.logger.error(f"Error in check_emails_and_notify: {str(e)}")

    def handle_email_notification(self, email_data):
        """Send the configured email notification, then try WhatsApp."""
        email_id = str(email_data['id'])
        subject = email_data.get('subject', 'No Subject')
        message = self.whatsapp_sender.format_email_message(email_data)

        if self.notification_state.is_whatsapp_terminal(email_id):
            self.logger.info(f"Notification already completed for email: {subject}")
            self.mark_email_seen(email_id, subject)
            return

        if not self.notification_state.has_email_sent(email_id):
            if not self.email_sender.send_email_notification(email_data):
                self.logger.error(
                    f"Email notification failed; WhatsApp will not be attempted for: {subject}"
                )
                return
            self.notification_state.record_email_sent(email_data, message)
        else:
            self.logger.info(f"Email notification already sent; not resending: {subject}")

        self.attempt_whatsapp_notification(email_data, message)

    def process_due_whatsapp_retries(self, exclude_email_ids=None):
        """Retry queued WhatsApp notifications without resending email."""
        exclude_email_ids = exclude_email_ids or set()
        due_notifications = self.notification_state.get_due_whatsapp_notifications(
            self.config.WHATSAPP_MAX_RETRIES
        )
        due_notifications = [
            entry for entry in due_notifications
            if str(entry.get('email_data', {}).get('id')) not in exclude_email_ids
        ]

        if not due_notifications:
            return

        self.logger.info(f"Processing {len(due_notifications)} due WhatsApp retry item(s)")

        for entry in due_notifications:
            email_data = entry.get('email_data')
            message = entry.get('message')
            if not email_data or not message:
                continue

            self.attempt_whatsapp_notification(email_data, message)

            if self.config.NOTIFICATION_DELAY_SECONDS:
                time.sleep(self.config.NOTIFICATION_DELAY_SECONDS)

    def attempt_whatsapp_notification(self, email_data, message):
        """Attempt WhatsApp delivery and update persisted retry state."""
        email_id = str(email_data['id'])
        subject = email_data.get('subject', 'No Subject')

        if self.notification_state.whatsapp_attempts_exhausted(
            email_id,
            self.config.WHATSAPP_MAX_RETRIES,
        ):
            self.logger.warning(f"WhatsApp retries exhausted for email: {subject}")
            self.notification_state.record_whatsapp_exhausted(email_id)
            self.mark_email_seen(email_id, subject)
            return False

        if not self.notification_state.is_whatsapp_due(email_id):
            self.logger.info(f"WhatsApp retry is not due yet for email: {subject}")
            return False

        if self.whatsapp_sender.send_immediate_message(message):
            self.notification_state.record_whatsapp_result(
                email_data,
                message,
                success=True,
                max_retries=self.config.WHATSAPP_MAX_RETRIES,
                retry_delay_seconds=self.config.WHATSAPP_RETRY_DELAY_SECONDS,
            )
            self.logger.info(f"WhatsApp notification sent for email: {subject}")
            self.mark_email_seen(email_id, subject)
            return True

        entry = self.notification_state.record_whatsapp_result(
            email_data,
            message,
            success=False,
            max_retries=self.config.WHATSAPP_MAX_RETRIES,
            retry_delay_seconds=self.config.WHATSAPP_RETRY_DELAY_SECONDS,
            error='WhatsApp send was not verified',
        )

        if entry.get('status') == 'exhausted':
            self.logger.error(f"WhatsApp retries exhausted for email: {subject}")
            self.mark_email_seen(email_id, subject)
        else:
            self.logger.warning(
                f"WhatsApp notification queued for retry; email remains unread: {subject}"
            )

        return False

    def mark_email_seen(self, email_id, subject):
        """Mark the source inbox email as seen and log failures."""
        if not self.email_monitor.mark_email_as_seen(email_id):
            self.logger.warning(
                f"Email could not be marked as seen and may be retried: {subject}"
            )
    
    def run_once(self):
        """Run the email check once"""
        if not self.validate_configuration():
            self.logger.error("Configuration validation failed. Please check your .env file.")
            return False
        
        self.logger.info("Running email check once...")
        try:
            self.check_emails_and_notify()
        finally:
            self.email_monitor.disconnect_from_email()
            self.whatsapp_sender.close()
        return True
    
    def run_scheduler(self):
        """Run the email checker on a schedule"""
        if not self.validate_configuration():
            self.logger.error("Configuration validation failed. Please check your .env file.")
            return
        
        # Schedule the email check
        schedule.every(self.config.CHECK_INTERVAL_MINUTES).minutes.do(self.check_emails_and_notify)
        
        self.logger.info(f"Email notification system started. Checking every {self.config.CHECK_INTERVAL_MINUTES} minutes.")
        self.logger.info("Press Ctrl+C to stop the system.")
        
        # Run the first check immediately
        self.check_emails_and_notify()
        
        # Keep the scheduler running
        try:
            while True:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("Email notification system stopped by user")
        finally:
            self.email_monitor.disconnect_from_email()
            self.whatsapp_sender.close()

def main():
    """Main function"""
    import sys
    
    notifier = EmailToWhatsAppNotifier()
    
    if len(sys.argv) > 1 and sys.argv[1] == '--once':
        # Run once and exit
        notifier.run_once()
    else:
        # Run continuously on schedule
        notifier.run_scheduler()

if __name__ == "__main__":
    main()
