#!/usr/bin/env python3
"""
Test email detection only (without WhatsApp)
"""

import logging
from email_monitor import EmailMonitor

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def test_email_detection():
    """Test email detection without WhatsApp"""
    monitor = EmailMonitor()
    
    print("Testing email detection...")
    emails = monitor.get_new_emails()
    
    if emails:
        print(f"\n✅ Found {len(emails)} unread email(s):")
        for i, email in enumerate(emails, 1):
            print(f"\nEmail {i}:")
            print(f"  Subject: {email['subject']}")
            print(f"  From: {email['sender']}")
            print(f"  Date: {email['date']}")
            print(f"  Preview: {email['body'][:100]}...")
    else:
        print("\n❌ No unread emails found")
    
    monitor.disconnect_from_email()

if __name__ == "__main__":
    test_email_detection()
