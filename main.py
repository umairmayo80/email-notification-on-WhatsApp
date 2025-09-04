#!/usr/bin/env python3
"""
Email to WhatsApp Notification System
Monitors email inbox and sends WhatsApp notifications for new emails
"""

import time
import schedule
import logging
from datetime import datetime
from email_monitor import EmailMonitor
from whatsapp_sender import WhatsAppSender
from config import Config

class EmailToWhatsAppNotifier:
    def __init__(self):
        self.email_monitor = EmailMonitor()
        self.whatsapp_sender = WhatsAppSender()
        self.config = Config()
        
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
        """Check for new emails and send WhatsApp notifications"""
        try:
            self.logger.info("Checking for new emails...")
            
            # Get new emails
            new_emails = self.email_monitor.get_new_emails()
            
            if not new_emails:
                self.logger.info("No new emails found")
                return
            
            self.logger.info(f"Found {len(new_emails)} new email(s)")
            
            # Send WhatsApp notification for each email
            for email_data in new_emails:
                message = self.whatsapp_sender.format_email_message(email_data)
                
                if self.whatsapp_sender.send_immediate_message(message):
                    self.logger.info(f"WhatsApp notification sent for email: {email_data['subject']}")
                else:
                    self.logger.error(f"Failed to send WhatsApp notification for email: {email_data['subject']}")
                
                # Add a small delay between messages to avoid overwhelming
                time.sleep(30)
        
        except Exception as e:
            self.logger.error(f"Error in check_emails_and_notify: {str(e)}")
    
    def run_once(self):
        """Run the email check once"""
        if not self.validate_configuration():
            self.logger.error("Configuration validation failed. Please check your .env file.")
            return False
        
        self.logger.info("Running email check once...")
        self.check_emails_and_notify()
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
