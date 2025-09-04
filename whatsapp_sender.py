import logging
from datetime import datetime, timedelta
from typing import Optional, Dict
from config import Config

# Try to import pywhatkit with error handling
try:
    import pywhatkit as pwk
    PYWHATKIT_AVAILABLE = True
except Exception as e:
    print(f"Warning: pywhatkit not available: {e}")
    PYWHATKIT_AVAILABLE = False

class WhatsAppSender:
    def __init__(self):
        self.config = Config()
        self.logger = logging.getLogger(__name__)
    
    def send_message(self, message: str, instant: bool = True) -> bool:
        """
        Send a WhatsApp message instantly or with scheduling
        
        Args:
            message: The message to send
            instant: If True, send instantly; if False, use scheduling
        
        Returns:
            bool: True if message was sent successfully, False otherwise
        """
        try:
            if not PYWHATKIT_AVAILABLE:
                self.logger.error("pywhatkit is not available due to network issues")
                return False
                
            if instant:
                # Send instantly using pywhatkit's instant method
                self.logger.info("Sending WhatsApp message instantly...")
                pwk.sendwhatmsg_instantly(
                    phone_no=self.config.WHATSAPP_PHONE_NUMBER,
                    message=message,
                    wait_time=10,  # Wait time for WhatsApp Web to load
                    tab_close=True  # Close the tab after sending
                )
                self.logger.info("WhatsApp message sent instantly!")
                return True
            else:
                # Fallback to scheduled sending
                current_time = datetime.now()
                send_time = current_time + timedelta(minutes=2)
                
                if send_time.second > 0:
                    send_time = send_time.replace(second=0, microsecond=0) + timedelta(minutes=1)
                
                hour = send_time.hour
                minute = send_time.minute
                
                pwk.sendwhatmsg(
                    phone_no=self.config.WHATSAPP_PHONE_NUMBER,
                    message=message,
                    time_hour=hour,
                    time_min=minute,
                    wait_time=15,
                    tab_close=True
                )
                
                self.logger.info(f"WhatsApp message scheduled for {hour:02d}:{minute:02d}")
                return True
            
        except Exception as e:
            self.logger.error(f"Failed to send WhatsApp message: {str(e)}")
            return False
    
    def send_immediate_message(self, message: str) -> bool:
        """
        Send a WhatsApp message instantly
        
        Args:
            message: The message to send
        
        Returns:
            bool: True if message was sent successfully, False otherwise
        """
        return self.send_message(message, instant=True)
    
    def validate_phone_number(self) -> bool:
        """
        Validate that the phone number is in the correct format
        
        Returns:
            bool: True if phone number is valid, False otherwise
        """
        phone = self.config.WHATSAPP_PHONE_NUMBER
        
        if not phone:
            self.logger.error("WhatsApp phone number not configured")
            return False
        
        # Basic validation - should start with + and contain only digits after that
        if not phone.startswith('+') or not phone[1:].replace(' ', '').isdigit():
            self.logger.error(f"Invalid phone number format: {phone}")
            self.logger.info("Phone number should be in format: +1234567890")
            return False
        
        return True
    
    def format_email_message(self, email_data: Dict) -> str:
        """Format email data into a clean WhatsApp message"""
        subject = email_data.get('subject', 'No Subject')
        sender = email_data.get('sender', 'Unknown Sender')
        body = email_data.get('body', '')
        
        # Clean and truncate body if too long
        if body:
            # Remove extra whitespace and clean up
            body = ' '.join(body.split())
            if len(body) > 150:
                body = body[:150] + "..."
        
        message = f"📧 New Email\n\n"
        message += f"From: {sender}\n"
        message += f"Subject: {subject}\n"
        if body:
            message += f"\nPreview: {body}"
        
        return message
