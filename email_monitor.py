import imaplib
import email
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from email.header import decode_header
from config import Config

class EmailMonitor:
    def __init__(self):
        self.config = Config()
        self.last_check_time = None
        self.connection = None
        
        # Set up logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('email_monitor.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def connect_to_email(self) -> bool:
        """Connect to the email server"""
        try:
            self.connection = imaplib.IMAP4_SSL(self.config.EMAIL_HOST, self.config.EMAIL_PORT)
            self.connection.login(self.config.EMAIL_USERNAME, self.config.EMAIL_PASSWORD)
            self.connection.select('INBOX')
            self.logger.info("Successfully connected to email server")
            return True
        except Exception as e:
            self.logger.error(f"Failed to connect to email server: {str(e)}")
            return False
    
    def disconnect_from_email(self):
        """Disconnect from the email server"""
        if self.connection:
            try:
                self.connection.close()
                self.connection.logout()
                self.connection = None
                self.logger.info("Disconnected from email server")
            except Exception as e:
                self.logger.error(f"Error disconnecting from email server: {str(e)}")
                self.connection = None
    
    def get_new_emails(self) -> List[Dict]:
        """Get new emails since last check with retry logic"""
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                # Reconnect if connection is stale or failed
                if not self.connection or retry_count > 0:
                    self.disconnect_from_email()
                    if not self.connect_to_email():
                        retry_count += 1
                        continue
                
                # Search for unseen emails from today only to avoid processing too many emails
                from datetime import date
                today = date.today().strftime('%d-%b-%Y')
                self.logger.info(f"Today's date for search: {today}")
                search_criteria = f'UNSEEN SINCE {today}'
                
                self.logger.info(f"Searching for emails with criteria: {search_criteria}")
                status, messages = self.connection.search(None, search_criteria)
                
                if status != 'OK':
                    self.logger.error("Failed to search for emails")
                    retry_count += 1
                    continue
                
                email_ids = messages[0].split()
                self.logger.info(f"Found {len(email_ids)} unseen emails total")
                
                # Limit to most recent 3 emails to avoid overwhelming WhatsApp
                email_ids = email_ids[-3:] if len(email_ids) > 3 else email_ids
                
                new_emails = []
                
                for i, email_id in enumerate(email_ids):
                    self.logger.info(f"Processing email {i+1}/{len(email_ids)}")
                    email_data = self.fetch_email(email_id)
                    if email_data and self.should_notify(email_data):
                        new_emails.append(email_data)
                        self.logger.info(f"Email matches notification criteria: {email_data['subject']}")
                    else:
                        if email_data:
                            self.logger.info(f"Email does not match criteria - Subject: '{email_data['subject']}', From: '{email_data['sender']}'")
                        else:
                            self.logger.info(f"Failed to fetch email data")
                
                self.last_check_time = datetime.now()
                self.logger.info(f"Found {len(new_emails)} emails that match notification criteria")
                return new_emails
                
            except Exception as e:
                self.logger.error(f"Error fetching new emails (attempt {retry_count + 1}): {str(e)}")
                retry_count += 1
                if retry_count < max_retries:
                    self.logger.info(f"Retrying in 2 seconds...")
                    import time
                    time.sleep(2)
                
        self.logger.error(f"Failed to fetch emails after {max_retries} attempts")
        return []
    
    def decode_email_header(self, header_value):
        """Decode email header that might be encoded"""
        if not header_value:
            return header_value
        
        try:
            decoded_parts = decode_header(header_value)
            decoded_string = ""
            
            for part, encoding in decoded_parts:
                if isinstance(part, bytes):
                    if encoding:
                        decoded_string += part.decode(encoding)
                    else:
                        decoded_string += part.decode('utf-8', errors='ignore')
                else:
                    decoded_string += part
            
            return decoded_string
        except Exception as e:
            self.logger.error(f"Error decoding header '{header_value}': {str(e)}")
            return header_value

    def fetch_email(self, email_id) -> Optional[Dict]:
        """Fetch and parse a specific email"""
        try:
            status, msg_data = self.connection.fetch(email_id, '(BODY.PEEK[])')
            
            if status != 'OK':
                return None
            
            email_body = msg_data[0][1]
            email_message = email.message_from_bytes(email_body)
            
            # Extract and decode email details
            subject = self.decode_email_header(email_message['Subject']) or 'No Subject'
            sender = self.decode_email_header(email_message['From']) or 'Unknown Sender'
            date = email_message['Date'] or 'Unknown Date'
            
            # Get email body
            body = self.get_email_body(email_message)
            
            return {
                'id': email_id.decode(),
                'subject': subject,
                'sender': sender,
                'date': date,
                'body': body[:500] + '...' if len(body) > 500 else body  # Truncate long bodies
            }
            
        except Exception as e:
            self.logger.error(f"Error fetching email {email_id}: {str(e)}")
            return None
    
    def get_email_body(self, email_message) -> str:
        """Extract and clean the body text from an email message"""
        body = ""
        
        if email_message.is_multipart():
            for part in email_message.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))
                
                if content_type == "text/plain" and "attachment" not in content_disposition:
                    try:
                        body = part.get_payload(decode=True).decode('utf-8')
                        break
                    except:
                        continue
        else:
            try:
                body = email_message.get_payload(decode=True).decode('utf-8')
            except:
                body = str(email_message.get_payload())
        
        # Clean up the body text
        if body:
            # Remove HTML tags if present
            import re
            body = re.sub(r'<[^>]+>', '', body)
            # Remove excessive whitespace and newlines
            body = re.sub(r'\n\s*\n', '\n', body)
            body = re.sub(r'\s+', ' ', body)
            # Remove special characters and clean up
            body = body.strip()
        
        return body
    
    def should_notify(self, email_data: Dict) -> bool:
        """Determine if this email should trigger a WhatsApp notification"""
        # If no specific senders and no keywords are configured, notify for all emails
        if not self.config.MONITOR_SPECIFIC_SENDERS and not self.config.KEYWORDS_TO_MONITOR:
            self.logger.info(f"No filters configured - notifying for all emails")
            return True
        
        # Check if we should monitor specific senders
        if self.config.MONITOR_SPECIFIC_SENDERS:
            sender_match = any(sender.lower() in email_data['sender'].lower() 
                             for sender in self.config.MONITOR_SPECIFIC_SENDERS)
            if sender_match:
                self.logger.info(f"Email matches monitored sender: {email_data['sender']}")
                return True
        
        # Check for keywords in subject or body
        if self.config.KEYWORDS_TO_MONITOR:
            text_to_search = f"{email_data['subject']} {email_data['body']}".lower()
            keyword_match = any(keyword.lower().strip() in text_to_search 
                              for keyword in self.config.KEYWORDS_TO_MONITOR)
            if keyword_match:
                self.logger.info(f"Email matches keyword filter")
                return True
        
        # If we have filters but none matched
        if self.config.MONITOR_SPECIFIC_SENDERS or self.config.KEYWORDS_TO_MONITOR:
            self.logger.info(f"Email does not match any configured filters")
            return False
        
        return True
    
    def format_notification_message(self, email_data: Dict) -> str:
        """Format the email data into a WhatsApp notification message"""
        message = f"📧 New Email Alert!\n\n"
        message += f"From: {email_data['sender']}\n"
        message += f"Subject: {email_data['subject']}\n"
        message += f"Date: {email_data['date']}\n\n"
        message += f"Preview: {email_data['body'][:200]}..."
        
        return message
