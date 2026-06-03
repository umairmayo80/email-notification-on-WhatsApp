import logging
import unittest
import warnings
from unittest.mock import patch

from email_monitor import EmailMonitor
from main import EmailToWhatsAppNotifier

warnings.filterwarnings('ignore', category=ResourceWarning)


class FakeEmailMonitor:
    def __init__(self, emails, mark_result=True):
        self.emails = emails
        self.mark_result = mark_result
        self.marked_seen = []

    def get_new_emails(self):
        return self.emails

    def mark_email_as_seen(self, email_id):
        self.marked_seen.append(email_id)
        return self.mark_result


class FakeWhatsAppSender:
    def __init__(self, send_result):
        self.send_result = send_result
        self.sent_messages = []

    def format_email_message(self, email_data):
        return f"Message for {email_data['subject']}"

    def send_immediate_message(self, message):
        self.sent_messages.append(message)
        return self.send_result


class FakeIMAPConnection:
    def __init__(self, store_status='OK', search_response=b'101', fetch_message=None):
        self.store_status = store_status
        self.search_response = search_response
        self.fetch_message = fetch_message or (
            b"Subject: Routine update\r\n"
            b"From: other@example.com\r\n"
            b"Date: Wed, 03 Jun 2026 09:00:00 +0000\r\n"
            b"Content-Type: text/plain; charset=utf-8\r\n"
            b"\r\n"
            b"This email should not match the configured sender filter."
        )
        self.uid_calls = []

    def uid(self, command, *args):
        self.uid_calls.append((command, args))

        if command == 'SEARCH':
            return 'OK', [self.search_response]
        if command == 'FETCH':
            return 'OK', [(b'101 (BODY[] {123}', self.fetch_message)]
        if command == 'STORE':
            return self.store_status, [b'']

        return 'NO', [b'Unsupported command']


class TestNotificationFlow(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def make_notifier(self, email_monitor, whatsapp_sender):
        notifier = EmailToWhatsAppNotifier.__new__(EmailToWhatsAppNotifier)
        notifier.email_monitor = email_monitor
        notifier.whatsapp_sender = whatsapp_sender
        notifier.logger = logging.getLogger('test_notification_flow')
        return notifier

    def make_email_monitor(self, connection):
        monitor = EmailMonitor.__new__(EmailMonitor)
        monitor.connection = connection
        monitor.last_check_time = None
        monitor.logger = logging.getLogger('test_email_monitor')
        return monitor

    def test_successful_whatsapp_send_marks_email_as_seen(self):
        email = {
            'id': '123',
            'subject': 'Important',
            'sender': 'sender@example.com',
            'date': 'Wed, 03 Jun 2026 09:00:00 +0000',
            'body': 'Body',
        }
        email_monitor = FakeEmailMonitor([email])
        whatsapp_sender = FakeWhatsAppSender(send_result=True)
        notifier = self.make_notifier(email_monitor, whatsapp_sender)

        with patch('main.time.sleep', return_value=None):
            notifier.check_emails_and_notify()

        self.assertEqual(email_monitor.marked_seen, ['123'])
        self.assertEqual(whatsapp_sender.sent_messages, ['Message for Important'])

    def test_failed_whatsapp_send_does_not_mark_email_as_seen(self):
        email = {
            'id': '456',
            'subject': 'Retry later',
            'sender': 'sender@example.com',
            'date': 'Wed, 03 Jun 2026 09:00:00 +0000',
            'body': 'Body',
        }
        email_monitor = FakeEmailMonitor([email])
        whatsapp_sender = FakeWhatsAppSender(send_result=False)
        notifier = self.make_notifier(email_monitor, whatsapp_sender)

        with patch('main.time.sleep', return_value=None):
            notifier.check_emails_and_notify()

        self.assertEqual(email_monitor.marked_seen, [])
        self.assertEqual(whatsapp_sender.sent_messages, ['Message for Retry later'])

    def test_filtered_out_email_is_not_marked_seen_during_fetch(self):
        monitor = self.make_email_monitor(FakeIMAPConnection())
        monitor.config = type(
            'TestConfig',
            (),
            {
                'MONITOR_SPECIFIC_SENDERS': ['boss@example.com'],
                'KEYWORDS_TO_MONITOR': [],
            },
        )

        emails = monitor.get_new_emails()

        self.assertEqual(emails, [])
        self.assertNotIn(
            'STORE',
            [command for command, _ in monitor.connection.uid_calls],
        )

    def test_mark_email_as_seen_returns_true_for_ok_store(self):
        monitor = self.make_email_monitor(FakeIMAPConnection(store_status='OK'))

        result = monitor.mark_email_as_seen('789')

        self.assertTrue(result)
        self.assertIn(
            ('STORE', ('789', '+FLAGS.SILENT', r'(\Seen)')),
            monitor.connection.uid_calls,
        )

    def test_mark_email_as_seen_returns_false_for_non_ok_store(self):
        monitor = self.make_email_monitor(FakeIMAPConnection(store_status='NO'))

        result = monitor.mark_email_as_seen('789')

        self.assertFalse(result)
        self.assertIn(
            ('STORE', ('789', '+FLAGS.SILENT', r'(\Seen)')),
            monitor.connection.uid_calls,
        )


if __name__ == '__main__':
    unittest.main()
