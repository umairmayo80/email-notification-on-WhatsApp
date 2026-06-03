import logging
import os
import tempfile
import unittest
import warnings
from unittest.mock import patch

import whatsapp_sender
from email_monitor import EmailMonitor
from main import EmailToWhatsAppNotifier
from notification_state import NotificationState
from whatsapp_sender import WhatsAppSender

warnings.filterwarnings('ignore', category=ResourceWarning)


def build_raw_email(subject='Routine update', sender='other@example.com', body='Body'):
    return (
        f"Subject: {subject}\r\n"
        f"From: {sender}\r\n"
        "Date: Wed, 03 Jun 2026 09:00:00 +0000\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        f"{body}"
    ).encode()


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
    def __init__(self, send_results, events=None):
        self.send_results = (
            list(send_results) if isinstance(send_results, list) else [send_results]
        )
        self.sent_messages = []
        self.events = events if events is not None else []

    def format_email_message(self, email_data):
        return f"Message for {email_data['subject']}"

    def send_immediate_message(self, message):
        self.sent_messages.append(message)
        self.events.append(f"whatsapp:{message}")
        return self.send_results.pop(0) if self.send_results else False


class FakeEmailNotificationSender:
    def __init__(self, send_result=True, events=None):
        self.send_result = send_result
        self.sent_email_ids = []
        self.events = events if events is not None else []

    def send_email_notification(self, email_data):
        self.sent_email_ids.append(str(email_data['id']))
        self.events.append(f"email:{email_data['id']}")
        return self.send_result


class FakeIMAPConnection:
    def __init__(
        self,
        store_status='OK',
        search_response=b'101',
        fetch_message=None,
        fetch_messages=None,
    ):
        self.store_status = store_status
        self.search_response = search_response
        self.fetch_message = fetch_message or build_raw_email(
            body='This email should not match the configured sender filter.'
        )
        self.fetch_messages = fetch_messages or {}
        self.uid_calls = []
        self.select_calls = []

    def select(self, mailbox):
        self.select_calls.append(mailbox)
        return 'OK', [b'']

    def uid(self, command, *args):
        self.uid_calls.append((command, args))

        if command == 'SEARCH':
            return 'OK', [self.search_response]
        if command == 'FETCH':
            email_uid = args[0].decode() if isinstance(args[0], bytes) else str(args[0])
            return 'OK', [
                (b'101 (BODY[] {123}', self.fetch_messages.get(email_uid, self.fetch_message))
            ]
        if command == 'STORE':
            return self.store_status, [b'']

        return 'NO', [b'Unsupported command']


class TestNotificationFlow(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def make_state(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return NotificationState(os.path.join(temp_dir.name, 'notification_state.json'))

    def make_notifier(
        self,
        email_monitor,
        whatsapp_sender,
        email_sender=None,
        notification_state=None,
        config=None,
    ):
        notifier = EmailToWhatsAppNotifier.__new__(EmailToWhatsAppNotifier)
        notifier.email_monitor = email_monitor
        notifier.email_sender = email_sender or FakeEmailNotificationSender()
        notifier.whatsapp_sender = whatsapp_sender
        notifier.notification_state = notification_state or self.make_state()
        notifier.config = config or type(
            'TestConfig',
            (),
            {
                'WHATSAPP_MAX_RETRIES': 3,
                'WHATSAPP_RETRY_DELAY_SECONDS': 0,
                'NOTIFICATION_DELAY_SECONDS': 0,
            },
        )
        notifier.logger = logging.getLogger('test_notification_flow')
        return notifier

    def make_email_monitor(self, connection):
        monitor = EmailMonitor.__new__(EmailMonitor)
        monitor.connection = connection
        monitor.last_check_time = None
        monitor.logger = logging.getLogger('test_email_monitor')
        return monitor

    def test_email_notification_is_sent_before_whatsapp(self):
        email = {
            'id': '123',
            'subject': 'Important',
            'sender': 'sender@example.com',
            'date': 'Wed, 03 Jun 2026 09:00:00 +0000',
            'body': 'Body',
        }
        events = []
        email_monitor = FakeEmailMonitor([email])
        email_sender = FakeEmailNotificationSender(events=events)
        whatsapp_sender = FakeWhatsAppSender(send_results=True, events=events)
        notifier = self.make_notifier(email_monitor, whatsapp_sender, email_sender)

        with patch('main.time.sleep', return_value=None):
            notifier.check_emails_and_notify()

        self.assertEqual(events, ['email:123', 'whatsapp:Message for Important'])
        self.assertEqual(email_monitor.marked_seen, ['123'])
        self.assertEqual(email_sender.sent_email_ids, ['123'])
        self.assertEqual(whatsapp_sender.sent_messages, ['Message for Important'])

    def test_email_success_and_whatsapp_failure_queues_retry_without_resending_email(self):
        email = {
            'id': '456',
            'subject': 'Retry later',
            'sender': 'sender@example.com',
            'date': 'Wed, 03 Jun 2026 09:00:00 +0000',
            'body': 'Body',
        }
        email_monitor = FakeEmailMonitor([email])
        email_sender = FakeEmailNotificationSender()
        whatsapp_sender = FakeWhatsAppSender(send_results=[False, False])
        state = self.make_state()
        notifier = self.make_notifier(email_monitor, whatsapp_sender, email_sender, state)

        with patch('main.time.sleep', return_value=None):
            notifier.check_emails_and_notify()
            notifier.check_emails_and_notify()

        self.assertEqual(email_monitor.marked_seen, [])
        self.assertEqual(email_sender.sent_email_ids, ['456'])
        self.assertEqual(
            whatsapp_sender.sent_messages,
            ['Message for Retry later', 'Message for Retry later'],
        )
        self.assertTrue(state.has_email_sent('456'))
        self.assertEqual(state.get('456')['status'], 'queued')
        self.assertEqual(state.get('456')['attempt_count'], 2)

    def test_whatsapp_success_marks_email_as_seen(self):
        email = {
            'id': '777',
            'subject': 'Done',
            'sender': 'sender@example.com',
            'date': 'Wed, 03 Jun 2026 09:00:00 +0000',
            'body': 'Body',
        }
        email_monitor = FakeEmailMonitor([email])
        whatsapp_sender = FakeWhatsAppSender(send_results=True)
        state = self.make_state()
        notifier = self.make_notifier(
            email_monitor,
            whatsapp_sender,
            FakeEmailNotificationSender(),
            state,
        )

        notifier.check_emails_and_notify()

        self.assertEqual(email_monitor.marked_seen, ['777'])
        self.assertEqual(state.get('777')['status'], 'sent')

    def test_exhausted_whatsapp_retries_mark_email_as_seen_after_email_delivery(self):
        email = {
            'id': '888',
            'subject': 'Exhaust retries',
            'sender': 'sender@example.com',
            'date': 'Wed, 03 Jun 2026 09:00:00 +0000',
            'body': 'Body',
        }
        config = type(
            'TestConfig',
            (),
            {
                'WHATSAPP_MAX_RETRIES': 1,
                'WHATSAPP_RETRY_DELAY_SECONDS': 0,
                'NOTIFICATION_DELAY_SECONDS': 0,
            },
        )
        email_monitor = FakeEmailMonitor([email])
        whatsapp_sender = FakeWhatsAppSender(send_results=False)
        state = self.make_state()
        notifier = self.make_notifier(
            email_monitor,
            whatsapp_sender,
            FakeEmailNotificationSender(),
            state,
            config,
        )

        notifier.check_emails_and_notify()

        self.assertEqual(email_monitor.marked_seen, ['888'])
        self.assertEqual(state.get('888')['status'], 'exhausted')

    def test_email_failure_does_not_attempt_whatsapp_or_mark_seen(self):
        email = {
            'id': '999',
            'subject': 'SMTP down',
            'sender': 'sender@example.com',
            'date': 'Wed, 03 Jun 2026 09:00:00 +0000',
            'body': 'Body',
        }
        email_monitor = FakeEmailMonitor([email])
        email_sender = FakeEmailNotificationSender(send_result=False)
        whatsapp_sender = FakeWhatsAppSender(send_results=True)
        notifier = self.make_notifier(email_monitor, whatsapp_sender, email_sender)

        notifier.check_emails_and_notify()

        self.assertEqual(email_monitor.marked_seen, [])
        self.assertEqual(whatsapp_sender.sent_messages, [])

    def test_filtered_out_email_is_not_marked_seen_during_fetch(self):
        monitor = self.make_email_monitor(FakeIMAPConnection())
        monitor.config = type(
            'TestConfig',
            (),
            {
                'MONITOR_SPECIFIC_SENDERS': ['boss@example.com'],
                'KEYWORDS_TO_MONITOR': [],
                'MAX_EMAILS_PER_CHECK': 3,
                'EMAIL_SCAN_MULTIPLIER': 5,
            },
        )

        emails = monitor.get_new_emails()

        self.assertEqual(emails, [])
        self.assertNotIn(
            'STORE',
            [command for command, _ in monitor.connection.uid_calls],
        )

    def test_email_monitor_respects_max_emails_per_check(self):
        connection = FakeIMAPConnection(search_response=b'101 102 103 104 105')
        monitor = self.make_email_monitor(connection)
        monitor.config = type(
            'TestConfig',
            (),
            {
                'MONITOR_SPECIFIC_SENDERS': [],
                'KEYWORDS_TO_MONITOR': [],
                'MAX_EMAILS_PER_CHECK': 2,
                'EMAIL_SCAN_MULTIPLIER': 5,
            },
        )

        emails = monitor.get_new_emails()
        fetched_uids = [
            args[0]
            for command, args in connection.uid_calls
            if command == 'FETCH'
        ]

        self.assertEqual(len(emails), 2)
        self.assertEqual(fetched_uids, ['105', '104'])

    def test_email_monitor_can_fetch_more_than_default_limit_when_configured(self):
        connection = FakeIMAPConnection(search_response=b'101 102 103 104 105')
        monitor = self.make_email_monitor(connection)
        monitor.config = type(
            'TestConfig',
            (),
            {
                'MONITOR_SPECIFIC_SENDERS': [],
                'KEYWORDS_TO_MONITOR': [],
                'MAX_EMAILS_PER_CHECK': 5,
                'EMAIL_SCAN_MULTIPLIER': 5,
            },
        )

        emails = monitor.get_new_emails()
        fetched_uids = [
            args[0]
            for command, args in connection.uid_calls
            if command == 'FETCH'
        ]

        self.assertEqual(len(emails), 5)
        self.assertEqual(fetched_uids, ['105', '104', '103', '102', '101'])

    def test_email_monitor_scans_past_batch_limit_for_matching_email(self):
        connection = FakeIMAPConnection(
            search_response=b'101 102 103 104 105',
            fetch_messages={
                '105': build_raw_email(subject='Noise 5', sender='other@example.com'),
                '104': build_raw_email(subject='Noise 4', sender='other@example.com'),
                '103': build_raw_email(subject='Important', sender='Boss <boss@example.com>'),
            },
        )
        monitor = self.make_email_monitor(connection)
        monitor.config = type(
            'TestConfig',
            (),
            {
                'MONITOR_SPECIFIC_SENDERS': ['boss@example.com'],
                'KEYWORDS_TO_MONITOR': [],
                'MAX_EMAILS_PER_CHECK': 1,
                'EMAIL_SCAN_MULTIPLIER': 5,
            },
        )

        emails = monitor.get_new_emails()
        fetched_uids = [
            args[0]
            for command, args in connection.uid_calls
            if command == 'FETCH'
        ]
        search_args = [
            args
            for command, args in connection.uid_calls
            if command == 'SEARCH'
        ][0]

        self.assertEqual([email['id'] for email in emails], ['103'])
        self.assertEqual(fetched_uids, ['105', '104', '103'])
        self.assertIn('UNSEEN', search_args)
        self.assertIn('SINCE', search_args)

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

    def make_whatsapp_sender(self):
        sender = WhatsAppSender.__new__(WhatsAppSender)
        sender.config = type(
            'TestConfig',
            (),
            {
                'WHATSAPP_PHONE_NUMBER': '+1234567890',
                'WHATSAPP_GROUP_INVITE_CODE': '',
                'WHATSAPP_CHROME_PROFILE_DIR': '.whatsapp_chrome_profile',
                'WHATSAPP_WAIT_SECONDS': 1,
                'CHROME_BINARY_PATH': None,
            },
        )
        sender.logger = logging.getLogger('test_whatsapp_sender')
        sender.driver = None
        return sender

    def test_chrome_options_use_configured_profile_dir(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        sender = self.make_whatsapp_sender()
        sender.config.WHATSAPP_CHROME_PROFILE_DIR = temp_dir.name

        options = sender._build_chrome_options()

        self.assertIn(f"--user-data-dir={os.path.abspath(temp_dir.name)}", options.arguments)

    def test_click_send_button_clicks_real_button(self):
        sender = self.make_whatsapp_sender()
        clicked = []

        class FakeButton:
            def click(self):
                clicked.append(True)

        class FakeWait:
            def __init__(self, *args, **kwargs):
                pass

            def until(self, condition):
                return FakeButton()

        with patch.object(whatsapp_sender, 'WebDriverWait', FakeWait):
            sender._click_send_button(driver=object())

        self.assertEqual(clicked, [True])

    def test_group_invite_url_overrides_phone_chat_url(self):
        sender = self.make_whatsapp_sender()
        sender.config.WHATSAPP_GROUP_INVITE_CODE = (
            'https://web.whatsapp.com/accept?code=GroupInvite123&utm_campaign=wa_chat_v2'
        )

        url = sender._build_chat_url('hello group')

        self.assertEqual(
            url,
            'https://web.whatsapp.com/accept?code=GroupInvite123',
        )

    def test_group_invite_code_allows_whatsapp_validation_without_phone(self):
        sender = self.make_whatsapp_sender()
        sender.config.WHATSAPP_PHONE_NUMBER = ''
        sender.config.WHATSAPP_GROUP_INVITE_CODE = 'GroupInvite123'

        self.assertTrue(sender.validate_phone_number())


if __name__ == '__main__':
    unittest.main()
